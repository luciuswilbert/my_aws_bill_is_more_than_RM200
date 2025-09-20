# lambda_function.py
import json
import base64
from bedrock import Bedrock
 
nova = Bedrock()
 
def lambda_handler(event, context):
    try:
        # Decode body if present
        body = event.get("body")
        if body:
            if event.get("isBase64Encoded", False):
                body = base64.b64decode(body).decode("utf-8")
            body = json.loads(body)
        else:
            body = {}
 
        action = body.get("action")
 
        if action == "chat":
            messages = body.get("messages", [])
            system = body.get("system", [])
            result, usage = nova.converse({"messages": messages, "system": system})
            return {
                "statusCode": 200,
                "headers": {"Content-Type": "application/json"},
                "body": json.dumps({"response": result, "usage": usage})
            }
 
        elif action == "embedding":
            text = body.get("text", "")
            embedding = nova.generate_embedding(text)
            return {
                "statusCode": 200,
                "headers": {"Content-Type": "application/json"},
                "body": json.dumps({"embedding": embedding})
            }
 
        else:
            return {
                "statusCode": 400,
                "body": json.dumps({"error": "Invalid action. Use 'chat' or 'embedding'."})
            }
 
    except Exception as e:
        return {
            "statusCode": 500,
            "body": json.dumps({"error": str(e)})
        }