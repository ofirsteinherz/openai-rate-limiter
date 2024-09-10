import json
import asyncio
from OpenAIGPTClient import OpenAIGPTClient
from GCRARateLimiter import GCRARateLimiter

# Load the limits JSON file
with open('limits.json') as f:
    model_limits = json.load(f)

async def send_requests(model, messages_list, max_tokens=50, debug=False, task_timeout=30, max_retries=3, batch_size=10):
    # Load limits based on the selected model
    limits = model_limits.get(model)
    if not limits:
        raise ValueError(f"Model {model} is not supported or limits are not available.")
    
    request_limit = limits["request_limit_per_minute"]
    token_limit = limits["token_limit_per_minute"]

    # Initialize the client and rate limiter
    client = OpenAIGPTClient(model=model, max_tokens=max_tokens, debug=debug)
    limiter = GCRARateLimiter(request_limit_per_minute=request_limit, token_limit_per_minute=token_limit, debug=debug)

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
                if debug:
                    print(f"Task {task_id}: Starting request with messages: {messages}", flush=True)

                # Calculate tokens for this request including 50% buffer on max_output_tokens
                num_tokens = limiter.calculate_token_usage(messages, max_tokens, model, max_output_tokens)
                total_input_tokens += num_tokens

                # Enforce rate limiting before making the request
                await limiter.enforce_rate_limit_async(num_tokens)

                if debug:
                    print(f"Task {task_id}: Rate limit passed, sending request.", flush=True)

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

                if debug:
                    print(f"Task {task_id}: Response received: {response} (Response tokens: {response_tokens})", flush=True)
                
                # Increment successful task counter
                total_successful_tasks += 1

                # Successful completion, break out of retry loop
                break

            except (asyncio.TimeoutError, aiohttp.ClientError) as e:
                attempt += 1
                if attempt < max_retries:
                    wait_time = 2 ** attempt  # Exponential backoff
                    if debug:
                        print(f"Task {task_id}: Retry {attempt}/{max_retries} after {wait_time} seconds due to error: {e}", flush=True)
                    await asyncio.sleep(wait_time)
                else:
                    if debug:
                        print(f"Task {task_id}: Failed after {max_retries} retries.", flush=True)
                    break
            except asyncio.CancelledError:
                if debug:
                    print(f"Task {task_id}: Cancelled.", flush=True)
                break
            except Exception as e:
                if debug:
                    print(f"Task {task_id}: Exception occurred: {e}", flush=True)
                break
            finally:
                if debug:
                    print(f"Task {task_id}: Completed or Cancelled.", flush=True)

    # Split messages into batches
    batches = [messages_list[i:i + batch_size] for i in range(0, len(messages_list), batch_size)]

    for batch_idx, batch in enumerate(batches):
        if debug:
            print(f"Processing batch {batch_idx + 1}/{len(batches)}...", flush=True)

        tasks = []
        task_to_message = {}  # Track messages associated with tasks
        for idx, messages in enumerate(batch):
            task = asyncio.create_task(send_single_request(messages, idx))
            tasks.append(task)
            task_to_message[task] = messages  # Map task to its corresponding message

        try:
            while tasks:
                # Wait for at least one task to complete and print the state
                done, pending = await asyncio.wait(tasks, timeout=1.0, return_when=asyncio.FIRST_COMPLETED)

                # Update the list of pending tasks
                tasks = [task for task in tasks if not task.done()]

                # Print details about pending tasks
                if debug:
                    print(f"Pending tasks: {len(pending)} | Completed tasks: {len(done)}", flush=True)

                # Print the current state of the token bucket
                if debug:
                    print(f"Token bucket state: {limiter.token_bucket}/{limiter.token_limit} tokens remaining", flush=True)

                # If all tasks are completed, break the loop
                if not tasks:
                    break

        except asyncio.CancelledError:
            print("All tasks were cancelled.", flush=True)

        finally:
            # Ensure tasks are cancelled properly if they are not done
            for task in tasks:
                if not task.done():
                    task.cancel()

            await asyncio.gather(*tasks, return_exceptions=True)
            print(f"Batch {batch_idx + 1}/{len(batches)} completed or cancelled.", flush=True)

    # Print summary
    print(f"Summary:", flush=True)
    print(f"Total tasks: {total_tasks}", flush=True)
    print(f"Total successful tasks: {total_successful_tasks}", flush=True)
    print(f"Total input tokens: {total_input_tokens}", flush=True)
    print(f"Total output tokens: {total_output_tokens}", flush=True)