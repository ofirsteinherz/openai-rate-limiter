import json
import asyncio
from OpenAIGPTClient import OpenAIGPTClient
from GCRARateLimiter import GCRARateLimiter
from custom_logger import CustomLogger
import aiohttp

# Load the limits JSON file
with open('limits.json') as f:
    model_limits = json.load(f)

async def send_requests(model, messages_list, max_tokens=50, debug=False, task_timeout=30, max_retries=3, batch_size=10):
    # Initialize custom logger
    logger = CustomLogger.initialize_from_env()

    # Load limits based on the selected model
    limits = model_limits.get(model)
    if not limits:
        logger.log("error", f"Model {model} is not supported or limits are not available.")
        raise ValueError(f"Model {model} is not supported or limits are not available.")
    
    request_limit = limits["request_limit_per_minute"]
    token_limit = limits["token_limit_per_minute"]

    # Initialize the client and rate limiter
    client = OpenAIGPTClient(model=model, max_tokens=max_tokens, debug=debug)
    limiter = GCRARateLimiter(request_limit_per_minute=request_limit, token_limit_per_minute=token_limit, debug=debug)

    logger.log("info", "Initialized client and rate limiter.")
    
    # Summary variables
    total_tasks = len(messages_list)
    total_input_tokens = 0
    total_output_tokens = 0
    total_successful_tasks = 0

    # Track max token usage of the outputs and add 50% buffer
    max_output_tokens = 0

    async def send_single_request(messages, task_id):
        nonlocal total_input_tokens, total_output_tokens, total_successful_tasks, max_output_tokens
        attempt = 0
        while attempt < max_retries:
            try:
                logger.log("info", f"Task {task_id}: Starting request with messages: {messages}")

                # Calculate tokens for this request including 50% buffer on max_output_tokens
                num_tokens = limiter.calculate_token_usage(messages, max_tokens, model, max_output_tokens)
                total_input_tokens += num_tokens

                # Enforce rate limiting before making the request
                await limiter.enforce_rate_limit_async(num_tokens)

                logger.log("info", f"Task {task_id}: Rate limit passed, sending request.")

                # Make the actual API call with a timeout to avoid hanging tasks
                response, response_tokens = await asyncio.wait_for(
                    client.make_api_call(messages),
                    timeout=task_timeout
                )

                # Count output tokens and adjust token usage
                total_output_tokens += response_tokens
                limiter.token_bucket -= response_tokens  # Deduct the output tokens from the bucket

                # Update max_output_tokens if current response tokens exceed the previous max
                if response_tokens > max_output_tokens:
                    max_output_tokens = response_tokens

                logger.log("info", f"Task {task_id}: Response received: {response} (Response tokens: {response_tokens})")
                
                # Increment successful task counter
                total_successful_tasks += 1

                # Successful completion, break out of retry loop
                break

            except (asyncio.TimeoutError, aiohttp.ClientError) as e:
                attempt += 1
                if attempt < max_retries:
                    wait_time = 2 ** attempt  # Exponential backoff
                    logger.log("warning", f"Task {task_id}: Retry {attempt}/{max_retries} after {wait_time} seconds due to error: {e}")
                    await asyncio.sleep(wait_time)
                else:
                    logger.log("error", f"Task {task_id}: Failed after {max_retries} retries.")
                    break
            except asyncio.CancelledError:
                logger.log("info", f"Task {task_id}: Cancelled.")
                break
            except Exception as e:
                logger.log("error", f"Task {task_id}: Exception occurred: {e}")
                break
            finally:
                logger.log("info", f"Task {task_id}: Completed or Cancelled.")

    # Split messages into batches
    batches = [messages_list[i:i + batch_size] for i in range(0, len(messages_list), batch_size)]

    for batch_idx, batch in enumerate(batches):
        logger.log("info", f"Processing batch {batch_idx + 1}/{len(batches)}...")

        tasks = []
        task_to_message = {}  # Track messages associated with tasks
        for idx, messages in enumerate(batch):
            task = asyncio.create_task(send_single_request(messages, idx))
            tasks.append(task)
            task_to_message[task] = messages  # Map task to its corresponding message

        try:
            while tasks:
                # Wait for at least one task to complete
                done, pending = await asyncio.wait(tasks, timeout=1.0, return_when=asyncio.FIRST_COMPLETED)

                # Update the list of pending tasks
                tasks = [task for task in tasks if not task.done()]

                # Log details about pending tasks
                logger.log("info", f"Pending tasks: {len(pending)} | Completed tasks: {len(done)}")

                # Log the current state of the token bucket
                logger.log("info", f"Token bucket state: {limiter.token_bucket}/{limiter.token_limit} tokens remaining")

                # If all tasks are completed, break the loop
                if not tasks:
                    break

        except asyncio.CancelledError:
            logger.log("warning", "All tasks were cancelled.")
        finally:
            # Ensure tasks are cancelled properly if they are not done
            for task in tasks:
                if not task.done():
                    task.cancel()

            await asyncio.gather(*tasks, return_exceptions=True)
            logger.log("info", f"Batch {batch_idx + 1}/{len(batches)} completed or cancelled.")

    # Log summary
    logger.log("info", "Summary:")
    logger.log("info", f"Total tasks: {total_tasks}")
    logger.log("info", f"Total successful tasks: {total_successful_tasks}")
    logger.log("info", f"Total input tokens: {total_input_tokens}")
    logger.log("info", f"Total output tokens: {total_output_tokens}")
