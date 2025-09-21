#!/usr/bin/env python3
"""
Convert MP4 video to Base64 and test API endpoint, then process with AWS Bedrock
"""
import base64
import json
import requests
import os
import boto3

def video_to_base64(video_path):
    """
    Convert video file to base64 string
    """
    try:
        with open(video_path, 'rb') as video_file:
            video_data = video_file.read()
            base64_string = base64.b64encode(video_data).decode('utf-8')
            return base64_string
    except Exception as e:
        print(f"Error reading video file: {str(e)}")
        return None

def test_api_with_base64(base64_data, filename, api_url):
    """
    Test the API with base64 video data
    """
    payload = {
        "video_data": base64_data,
        "filename": filename
    }
    
    headers = {
        'Content-Type': 'application/json'
    }
    
    # Configure proxy settings if needed
    proxies = {
        'http': None,
        'https': None
    }
    
    try:
        print("Sending request to API...")
        print(f"Payload size: {len(json.dumps(payload))} characters")
        
        # Try with proxy bypass
        response = requests.post(api_url, json=payload, headers=headers, proxies=proxies, timeout=300)
        
        print(f"Status Code: {response.status_code}")
        print(f"Response Headers: {dict(response.headers)}")
        print(f"Response Body: {response.text}")
        
        return response.json() if response.content else None
        
    except Exception as e:
        print(f"Error calling API: {str(e)}")
        return None

def save_base64_to_file(base64_string, output_file):
    """
    Save base64 string to file for reuse
    """
    try:
        with open(output_file, 'w') as f:
            f.write(base64_string)
        print(f"Base64 string saved to: {output_file}")
    except Exception as e:
        print(f"Error saving base64 file: {str(e)}")

def load_base64_from_file(input_file):
    """
    Load base64 string from file
    """
    try:
        with open(input_file, 'r') as f:
            return f.read().strip()
    except Exception as e:
        print(f"Error loading base64 file: {str(e)}")
        return None

def process_text_with_bedrock(transcript_text, filename="video_file"):
    """
    Process the transcribed text with AWS Bedrock flow
    """
    try:
        print("\n=== Processing with AWS Bedrock Flow ===")
        
        # Initialize Bedrock Agent Runtime client
        client = boto3.client("bedrock-agent-runtime")
        
        # Flow + Alias IDs
        flow_id = "CJB0RNM9XM"
        flow_alias = "I4LBMMG8G8"
        
        # Build input document
        input_document = {
            "content": transcript_text,
            "country": "Malaysia",
            "file_type": "video"
        }
        
        print(f"Sending transcript to Bedrock flow...")
        print(f"Content preview: {transcript_text[:100]}...")
        
        # Invoke the flow
        response = client.invoke_flow(
            flowIdentifier=flow_id,
            flowAliasIdentifier=flow_alias,
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
        

        print("=== Bedrock Flow Response Stream ===")
        for event in response["responseStream"]:
            # Each event is a dict with exactly one key
            for event_type, event_value in event.items():
                if event_type == "flowOutputEvent":
                    print(">>> Flow Output:")
                    print(json.dumps(event_value, indent=2))
                elif event_type == "traceEvent":
                    print(">>> Trace Event:")
                    print(json.dumps(event_value, indent=2))
                elif event_type == "flowCompletionEvent":
                    print(">>> Flow completed")
                elif event_type == "exception":
                    print(">>> Exception:")
                    print(json.dumps(event_value, indent=2))
        
        
    except Exception as e:
        print(f"Error processing with Bedrock: {str(e)}")
        return None

def main():
    # Configuration
    video_path = "test_video.mp4"  # Your video file
    api_url = "https://4fjmeet9lh.execute-api.us-east-1.amazonaws.com/V1"  # Updated API URL
    base64_output_file = "test_video_base64.txt"
    
    print("=== Video to Base64 Converter and API Tester ===\n")
    
    # Check if video file exists
    if not os.path.exists(video_path):
        print(f"Error: Video file '{video_path}' not found!")
        print("Make sure the file exists in the current directory.")
        return
    
    # Get file size
    file_size = os.path.getsize(video_path)
    print(f"Video file: {video_path}")
    print(f"File size: {file_size:,} bytes ({file_size/1024/1024:.2f} MB)")
    
    # Check if base64 file already exists
    if os.path.exists(base64_output_file):
        print(f"\nFound existing base64 file: {base64_output_file}")
        choice = input("Use existing base64 file? (y/n): ").lower().strip()
        
        if choice == 'y':
            print("Loading base64 from file...")
            base64_string = load_base64_from_file(base64_output_file)
            if not base64_string:
                return
        else:
            print("Converting video to base64...")
            base64_string = video_to_base64(video_path)
            if not base64_string:
                return
            save_base64_to_file(base64_string, base64_output_file)
    else:
        # Convert video to base64
        print("Converting video to base64...")
        base64_string = video_to_base64(video_path)
        
        if not base64_string:
            return
        
        # Save base64 for future use
        save_base64_to_file(base64_string, base64_output_file)
    
    print(f"Base64 length: {len(base64_string):,} characters")
    print(f"Base64 preview: {base64_string[:100]}...")
    
    # Test the API
    print(f"\nTesting API endpoint: {api_url}")
    result = test_api_with_base64(base64_string, os.path.basename(video_path), api_url)
    
    if result:
        print("\n=== API Response ===")
        print(json.dumps(result, indent=2))
        
        if result.get('success'):
            print(f"\n✅ SUCCESS: {result.get('message', 'Transcription completed')}")
            if 'transcript' in result:
                transcript_text = result['transcript']
                print(f"\n📝 TRANSCRIPT:\n{transcript_text}")
                
                # Process with Bedrock flow
                bedrock_result = process_text_with_bedrock(transcript_text, os.path.basename(video_path))
                
                return {
                    'transcript': transcript_text,
                    'bedrock_analysis': bedrock_result
                }
        else:
            print(f"\n❌ ERROR: {result.get('error', 'Unknown error')}")
    else:
        print("\n❌ Failed to get response from API")

def test_pipeline_only():
    """
    Test just the pipeline connection without video
    """
    api_url = "https://4fjmeet9lh.execute-api.us-east-1.amazonaws.com/V1"  # Updated API URL
    
    payload = {
        "test_pipeline": True
    }
    
    headers = {
        'Content-Type': 'application/json'
    }
    
    # Configure proxy settings if needed
    proxies = {
        'http': None,
        'https': None
    }
    
    try:
        print("Testing pipeline connection...")
        response = requests.post(api_url, json=payload, headers=headers, proxies=proxies, timeout=30)
        
        print(f"Status Code: {response.status_code}")
        print(f"Response: {response.text}")
        
        return response.json() if response.content else None
        
    except Exception as e:
        print(f"Error testing pipeline: {str(e)}")
        return None

if __name__ == "__main__":
    import sys
    
    if len(sys.argv) > 1 and sys.argv[1] == "test":
        # Just test pipeline connection
        result = test_pipeline_only()
        if result:
            print(json.dumps(result, indent=2))
    else:
        # Full video conversion and test
        result = main()
        
        if result and isinstance(result, dict):
            print("\n" + "="*50)
            print("FINAL RESULTS:")
            print("="*50)
            
            if 'transcript' in result:
                print(f"\n📝 TRANSCRIPT:\n{result['transcript']}")
            
            if 'bedrock_analysis' in result and result['bedrock_analysis']:
                print(f"\n🔍 BEDROCK ANALYSIS COMPLETED")
                print("Check the detailed output above for analysis results.")
        elif result:
            print(f"\nResult: {result}")
        