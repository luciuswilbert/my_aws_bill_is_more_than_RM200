"""
Image to Text Pipeline using Amazon Nova Pro
Simple flow: Image -> Bedrock (Nova Pro) -> Text Description
"""
import boto3
import json
import os
import base64
from dotenv import load_dotenv

load_dotenv()

class ImageToTextPipeline:
    def __init__(self, model_id='us.amazon.nova-pro-v1:0'):
        """
        Initializes the pipeline with a Bedrock runtime client.
        """
        self.region = os.getenv('AWS_DEFAULT_REGION', 'us-east-1')
        self.bedrock_runtime = boto3.client('bedrock-runtime', region_name=self.region)
        self.model_id = model_id

    def _get_image_format(self, image_file_path):
        """Determines the image format from its file extension."""
        ext = os.path.splitext(image_file_path)[1].lower()
        if ext in ['.jpg', '.jpeg']:
            return 'jpeg'
        elif ext == '.png':
            return 'png'
        elif ext == '.webp':
            return 'webp'
        elif ext == '.gif':
            return 'gif'
        else:
            raise ValueError(f"Unsupported image format: {ext}")

    def describe_image(self, image_file_path, prompt="Describe this image in detail."):
        try:
            with open(image_file_path, "rb") as f:
                image_data = f.read()
            base64_image_data = base64.b64encode(image_data).decode('utf-8')
            image_format = self._get_image_format(image_file_path)

            # System instructions
            system_list = [
                {"text": "You are an expert image analyst. Provide a detailed description of the image including objects, people, activities, setting, and any notable details."}
            ]

            # User message with image and text prompt
            message_list = [
                {
                    "role": "user",
                    "content": [
                        {
                            "image": {
                                "format": image_format,
                                "source": {"bytes": base64_image_data}
                            }
                        },
                        {
                            "text": prompt
                        }
                    ]
                }
            ]

            # Inference parameters
            inference_config = {
                "maxTokens": 10240,
                "temperature": 0.3,
                "topP": 0.9
            }

            # Full request payload
            native_request = {
                "schemaVersion": "messages-v1",
                "system": system_list,
                "messages": message_list,
                "inferenceConfig": inference_config
            }

            # Invoke Nova Pro
            response = self.bedrock_runtime.invoke_model(
                modelId=self.model_id,
                body=json.dumps(native_request),
                contentType='application/json',
                accept='application/json'
            )

            response_body = json.loads(response['body'].read())
            description = response_body["output"]["message"]["content"][0]["text"]
            return description

        except Exception as e:
            print(f"Error describing image: {e}")
            return None


class BedrockFlowInvoker:
    """
    Invokes a Bedrock Flow for cultural analysis.
    """
    def __init__(self, flow_id="CJB0RNM9XM", flow_alias="I4LBMMG8G8"):
        """
        Initializes the invoker with a Bedrock Agent Runtime client.
        """
        self.region = os.getenv('AWS_DEFAULT_REGION', 'us-east-1')
        self.client = boto3.client("bedrock-agent-runtime", region_name=self.region)
        self.flow_id = flow_id
        self.flow_alias = flow_alias

    def invoke_cultural_analysis_flow(self, text_content, country="Malaysia", file_type="image"):
        """
        Invokes the cultural analysis flow with the given text content
        and streams the response.
        """
        try:
            # Build input document based on the user's example
            input_document = {
                "content": text_content,
                "country": country,
                "file_type": file_type
            }

            # Invoke the flow
            response = self.client.invoke_flow(
                flowIdentifier=self.flow_id,
                flowAliasIdentifier=self.flow_alias,
                enableTrace=True,
                inputs=[
                    {
                        "content": {
                            "document": input_document
                        },
                        "nodeName": "FlowInputNode",
                        "nodeOutputName": "document"
                    }
                ]
            )

            final_output = None
            for event in response["responseStream"]:
                # Each event is a dict with exactly one key
                for event_type, event_value in event.items():
                    if event_type == "flowOutputEvent":
                        # The output is nested under 'content' and then 'document'
                        output_value = event_value.get('content', {}).get('document')
                        if output_value:
                            final_output = output_value
                    elif event_type == "exception":
                        # In a server environment, this should be logged properly.
                        print(f"Exception received from Bedrock Flow: {json.dumps(event_value)}")

            return final_output

        except Exception as e:
            print(f"Error invoking Bedrock Flow: {e}")
            return None


def process_image_and_get_analysis(image_path: str) -> dict:
    """
    Processes a single image file to generate a description and then runs
    it through a cultural analysis Bedrock Flow. This function is designed
    to be used in a server setting like FastAPI.

    Args:
        image_path (str): The path to the image file.

    Returns:
        dict: A dictionary containing the analysis result or an error message.
    """
    print(f"Step 1: Generating description for image '{image_path}'...")
    pipeline = ImageToTextPipeline()
    description = pipeline.describe_image(image_path)

    if not description:
        print("...failed to generate description.")
        return {"error": "Failed to generate image description."}
    print("...description generated successfully.")

    print("Step 2: Invoking cultural analysis flow...")
    flow_invoker = BedrockFlowInvoker()
    flow_result = flow_invoker.invoke_cultural_analysis_flow(description)

    if not flow_result:
        print("...failed to get result from Bedrock Flow.")
        return {"error": "Failed to get result from Bedrock Flow."}
    print("...analysis received successfully.")

    return flow_result


def main():
    image_extensions = ['.jpg', '.jpeg', '.png', '.webp', '.gif']
    image_files = [f for f in os.listdir('.') if os.path.splitext(f)[1].lower() in image_extensions]

    if image_files:
        image_file = image_files[0]
        print(f"Found image: {image_file}. Starting analysis pipeline...")

        # The new function encapsulates the entire pipeline and returns a dictionary.
        analysis_result = process_image_and_get_analysis(image_file)

        # Print the final JSON object as the output, as requested.
        print("\n--- Final Analysis Result (JSON) ---")
        print(json.dumps(analysis_result, indent=2))
        print("------------------------------------")
    else:
        print(f"No image files with extensions ({', '.join(image_extensions)}) found in the current directory.")


if __name__ == "__main__":
    main()
