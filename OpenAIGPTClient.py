import os
import aiohttp
from dotenv import load_dotenv
from custom_logger import CustomLogger

# Load environment variables from the .env file
print("Loading environment variables...", flush=True)
load_dotenv()

class OpenAIGPTClient:
    def __init__(self, model, max_tokens=500, temperature=0.3, seed=42, debug=False):
        self.api_key = os.getenv('OPENAI_API_KEY')
        self.debug = debug
        self.model = model
        self.max_tokens = max_tokens
        self.temperature = temperature
        self.seed = seed
        self.logger = CustomLogger.get_instance()

        if not self.api_key:
            self.logger.log("error", "API key is not set. Please set the OPENAI_API_KEY environment variable.")
            raise ValueError("API key is not set. Please set the OPENAI_API_KEY environment variable.")
        self.endpoint = "https://api.openai.com/v1/chat/completions"
        self.logger.log("info", f"Client initialized with model: {self.model}.")

    async def make_api_call(self, messages):
        """Handles making the actual API call asynchronously using aiohttp."""
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}"
        }
        data = {
            "model": self.model,
            "messages": messages,
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
            "seed": self.seed
        }

        async with aiohttp.ClientSession() as session:
            try:
                self.logger.log("info", f"Sending request for model: {self.model} with {self.max_tokens} max tokens")

                async with session.post(self.endpoint, headers=headers, json=data) as response:
                    response.raise_for_status()  # Raise an error for bad responses

                    result = await response.json()

                    # Calculate the total tokens used
                    response_tokens = len(result['choices'][0]['message']['content'].split())
                    self.logger.log("info", f"Response tokens: {response_tokens}")

                    return result['choices'][0]['message']['content'].strip(), response_tokens

            except aiohttp.ClientError as http_err:
                self.logger.log("error", f"HTTP error occurred: {http_err}")
                return f"HTTP error occurred: {http_err}", 0
            except Exception as err:
                self.logger.log("error", f"An error occurred: {err}")
                return f"An error occurred: {err}", 0