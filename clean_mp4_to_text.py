"""
Direct MP4 to Text Pipeline - No MediaConvert needed
Uses Amazon Transcribe's native MP4 support
"""
import boto3
import json
import time
import os
import requests
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

class MP4ToTextPipeline:
    def __init__(self):
        self.region = os.getenv('AWS_DEFAULT_REGION', 'us-east-1')
        self.bucket = os.getenv('S3_BUCKET_NAME', 'video-bucket-ken')
        
        self.s3 = boto3.client('s3')
        self.transcribe = boto3.client('transcribe')
        
        print(f"✅ Ready to process MP4 → Text for bucket: {self.bucket}")
    
    def upload_video(self, video_file):
        """Upload MP4 to S3"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        s3_key = f"videos/{timestamp}_{os.path.basename(video_file)}"
        
        self.s3.upload_file(video_file, self.bucket, s3_key)
        return s3_key
    
    def start_transcription(self, video_s3_key, language_code=None):
        """Start transcription of MP4 file with automatic language detection"""
        base_name = os.path.splitext(os.path.basename(video_s3_key))[0]
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        job_name = f"transcribe_{base_name}_{timestamp}"
        
        job_params = {
            'TranscriptionJobName': job_name,
            'MediaFormat': 'mp4',
            'Media': {
                'MediaFileUri': f"s3://{self.bucket}/{video_s3_key}"
            },
            'OutputBucketName': self.bucket,
            'OutputKey': f"transcripts/{base_name}_transcript.json"
        }
        
        # Use automatic language detection or specified language
        if language_code:
            job_params['LanguageCode'] = language_code
            print(f"🌍 Using specified language: {language_code}")
        else:
            # Enable automatic language identification
            job_params['IdentifyLanguage'] = True
            # Optionally specify candidate languages to improve accuracy
            job_params['LanguageOptions'] = [
                'en-US', 'es-ES', 'fr-FR', 'de-DE', 'it-IT', 'pt-BR', 
                'ja-JP', 'ko-KR', 'zh-CN', 'ar-SA', 'hi-IN', 'ru-RU',
                'ms-MY', 'th-TH', 'vi-VN', 'id-ID', 'tl-PH'
            ]
            print("🌍 Using automatic language detection")
        
        self.transcribe.start_transcription_job(**job_params)
        return job_name
    
    def wait_for_transcription(self, job_name):
        """Wait for transcription to complete"""
        while True:
            response = self.transcribe.get_transcription_job(TranscriptionJobName=job_name)
            job = response['TranscriptionJob']
            status = job['TranscriptionJobStatus']
            
            if status == 'COMPLETED':
                return job
            elif status == 'FAILED':
                return None
            else:
                time.sleep(10)
    
    def save_transcript_text(self, transcription_job):
        """Get transcript JSON from S3 and extract text"""
        try:
            job_name = transcription_job['TranscriptionJobName']
            
            output_key = transcription_job.get('TranscriptionJob', {}).get('OutputKey')
            if output_key:
                json_s3_key = output_key
            else:
                json_s3_key = f"{job_name}.json"
            
            response = self.s3.get_object(Bucket=self.bucket, Key=json_s3_key)
            transcript_data = json.loads(response['Body'].read().decode('utf-8'))
            
            text = transcript_data['results']['transcripts'][0]['transcript']
            
            # Check for language identification results
            language_info = ""
            if 'results' in transcript_data and 'language_identification' in transcript_data['results']:
                lang_results = transcript_data['results']['language_identification']
                if lang_results:
                    detected_lang = lang_results[0]['language_code']
                    confidence = lang_results[0]['score']
                    language_info = f"🌍 Detected Language: {detected_lang} (confidence: {confidence:.2f})"
                    print(language_info)
            
            if not text.strip():
                text = "[No speech detected in the audio]"
            
            return text, language_info
            
        except Exception:
            try:
                job_name = transcription_job['TranscriptionJobName']
                
                response = self.s3.list_objects_v2(
                    Bucket=self.bucket,
                    Prefix="transcripts/"
                )
                
                json_files = []
                if 'Contents' in response:
                    for obj in response['Contents']:
                        key = obj['Key']
                        if key.endswith('.json'):
                            json_files.append(key)
                
                if json_files:
                    json_files.sort(key=lambda x: self.s3.head_object(Bucket=self.bucket, Key=x)['LastModified'], reverse=True)
                    
                    for json_file in json_files:
                        try:
                            response = self.s3.get_object(Bucket=self.bucket, Key=json_file)
                            transcript_data = json.loads(response['Body'].read().decode('utf-8'))
                            
                            file_job_name = transcript_data.get('jobName', '')
                            if file_job_name == job_name or job_name.split('_')[1] in json_file:
                                text = transcript_data['results']['transcripts'][0]['transcript']
                                
                                # Check for language identification
                                language_info = ""
                                if 'results' in transcript_data and 'language_identification' in transcript_data['results']:
                                    lang_results = transcript_data['results']['language_identification']
                                    if lang_results:
                                        detected_lang = lang_results[0]['language_code']
                                        confidence = lang_results[0]['score']
                                        language_info = f"🌍 Detected Language: {detected_lang} (confidence: {confidence:.2f})"
                                        print(language_info)
                                
                                return text, language_info
                                
                        except Exception:
                            continue
                
                return None, ""
                
            except Exception:
                return None, ""
                # Fallback: construct the key based on the job name
                json_s3_key = f"{job_name}.json"
                print(f"🔍 Constructed key: {json_s3_key}")
            
            print(f"� Looking for: s3://{self.bucket}/{json_s3_key}")
            
            # Use boto3 S3 to get the JSON file
            response = self.s3.get_object(Bucket=self.bucket, Key=json_s3_key)
            transcript_data = json.loads(response['Body'].read().decode('utf-8'))
            
            print("✅ Step 4: JSON result retrieved from S3")
            
            # Step 5: Extract result and show text
            print("📝 Step 5: Extracting result and showing text...")
            
            text = transcript_data['results']['transcripts'][0]['transcript']
            
            if not text.strip():
                text = "[No speech detected in the audio]"
            
            print(f"✅ Step 5: Text extracted successfully")
            print(f"📊 Text length: {len(text)} characters")
            
            return text, json_s3_key
            
        except Exception as e:
            print(f"❌ Error in steps 4-5: {e}")
            
            # Try to find the JSON file by listing all files and matching
            try:
                print("🔄 Searching for transcript files...")
                job_name = transcription_job['TranscriptionJobName']
                
                # List all files in the bucket with transcripts prefix
                response = self.s3.list_objects_v2(
                    Bucket=self.bucket,
                    Prefix="transcripts/"
                )
                
                print("📁 Available transcript files:")
                json_files = []
                if 'Contents' in response:
                    for obj in response['Contents']:
                        key = obj['Key']
                        print(f"   - {key}")
                        if key.endswith('.json'):
                            json_files.append(key)
                
                # Try to find the most recent JSON file that matches our job
                if json_files:
                    # Sort by last modified (most recent first)
                    json_files.sort(key=lambda x: self.s3.head_object(Bucket=self.bucket, Key=x)['LastModified'], reverse=True)
                    
                    for json_file in json_files:
                        try:
                            print(f"🎯 Trying file: {json_file}")
                            response = self.s3.get_object(Bucket=self.bucket, Key=json_file)
                            transcript_data = json.loads(response['Body'].read().decode('utf-8'))
                            
                            # Check if this is our job by comparing job names
                            file_job_name = transcript_data.get('jobName', '')
                            if file_job_name == job_name or job_name.split('_')[1] in json_file:
                                text = transcript_data['results']['transcripts'][0]['transcript']
                                print("✅ Found matching transcript!")
                                return text, json_file
                                
                        except Exception as file_error:
                            print(f"   ❌ Error reading {json_file}: {file_error}")
                            continue
                
                print("❌ No matching transcript found")
                return None, None
                
            except Exception as e2:
                print(f"❌ Search method also failed: {e2}")
                return None, None
    
    def process_video(self, video_file, language_code=None):
        """
        MP4 TO TEXT FLOW:
        1. Upload to S3
        2. MP4 directly to transcript (with automatic language detection)
        3. Return JSON file
        4. Use boto S3 to get JSON result
        5. Extract result and show text
        """
        print("🚀 MP4 TO TEXT FLOW")
        print("=" * 40)
        print("Flow: MP4 → S3 → Transcribe → JSON → Text")
        print("=" * 40)
        
        try:
            # Step 1: Upload to S3
            print("\n📤 Step 1: Upload to S3")
            video_s3_key = self.upload_video(video_file)
            
            # Step 2: MP4 directly to transcript
            print("\n🎤 Step 2: MP4 directly to transcript")
            job_name = self.start_transcription(video_s3_key, language_code)
            
            # Step 3: Return JSON file (wait for completion)
            print("\n⏳ Step 3: Wait for JSON file creation")
            transcription_result = self.wait_for_transcription(job_name)
            
            if not transcription_result:
                print("❌ Transcription failed")
                return None
            
            # Steps 4 & 5: Get JSON and extract text
            text, json_s3_key = self.save_transcript_text(transcription_result)
            
            if not text:
                print("❌ Text extraction failed")
                return None
            
            print("\n🎉 FLOW COMPLETED!")
            print("=" * 25)
            print(f"📁 Video: s3://{self.bucket}/{video_s3_key}")
            print(f"� JSON: s3://{self.bucket}/{json_s3_key}")
            print("\n� EXTRACTED TEXT:")
            print("-" * 50)
            print(text)
            print("-" * 50)
            
            return text
            
        except Exception as e:
            print(f"❌ Flow failed: {e}")
            return None

def main():
    pipeline = MP4ToTextPipeline()
    
    # Find MP4 files
    mp4_files = [f for f in os.listdir('.') if f.endswith('.mp4')]
    
    if mp4_files:
        video_file = mp4_files[0]
        print(f"🎬 Processing: {video_file}")
        
        result = pipeline.process_video(video_file)
        if result:
            print(f"\n✅ SUCCESS!")
        else:
            print(f"\n❌ FAILED!")
    else:
        print("❌ No MP4 files found in current directory")

if __name__ == "__main__":
    main()
