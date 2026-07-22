from schemas import AIplatform
from google import genai
from openai import OpenAI


class Gemini(AIplatform):
    def __init__(self, api_key: str, system_prompt: str = None) -> None:
        self.api_key = api_key
        self.client = genai.Client(api_key=self.api_key)
        self.system_prompt = system_prompt
        self.model = "gemini-3.5-flash"
        self.image_model = "gemini-2.5-flash-image"

    def chat(self, prompt: str):
        if self.system_prompt:
            prompt = f"{self.system_prompt}\n\n{prompt}"
        response = self.client.models.generate_content(model=self.model, contents=prompt)
        return response.text

    def generate_image(self, prompt: str) -> tuple[bytes, str]:
        response = self.client.models.generate_content(model=self.image_model, contents=prompt)
        for part in response.candidates[0].content.parts:
            if part.inline_data:
                return part.inline_data.data, part.inline_data.mime_type
        raise ValueError("The model did not return an image for this prompt.")


class Myopenai(AIplatform):
    def __init__(self, api_key: str, system_prompt: str = None) -> None:
        self.api_key = api_key
        self.client = OpenAI(api_key=self.api_key)
        self.system_prompt = system_prompt
        self.model = "gpt-4.1-mini"
 

    def chat(self, prompt: str):
        messages = []

        if self.system_prompt:
            messages.append({
                "role": "system",
                "content": self.system_prompt
            })

        messages.append({
            "role": "user",
            "content": prompt
        })

        response = self.client.chat.completions.create(
            model=self.model,
            messages=messages
        )

        return response.choices[0].message.content