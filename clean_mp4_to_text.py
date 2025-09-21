"""
Clean MP4 to Text Pipeline
Simple flow: MP4 → S3 → Transcribe → Extract Text
"""
import boto3
import json
import time
import os
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

class MP4ToTextPipeline:
    def __init__(self):
        self.region = os.getenv('AWS_DEFAULT_REGION', 'us-east-1')
        self.bucket = os.getenv('S3_BUCKET_NAME', 'video-bucket-ken')
        
        self.s3 = boto3.client('s3')
        self.transcribe = boto3.client('transcribe')
    
    def upload_video(self, video_file):
        """Upload MP4 to S3"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        s3_key = f"videos/{timestamp}_{os.path.basename(video_file)}"
        
        self.s3.upload_file(video_file, self.bucket, s3_key)
        return s3_key
    
    def start_transcription(self, video_s3_key):
        """Start transcription of MP4 file"""
        base_name = os.path.splitext(os.path.basename(video_s3_key))[0]
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        job_name = f"transcribe_{base_name}_{timestamp}"
        
        job_params = {
            'TranscriptionJobName': job_name,
            'LanguageCode': 'en-US',
            'MediaFormat': 'mp4',
            'Media': {
                'MediaFileUri': f"s3://{self.bucket}/{video_s3_key}"
            },
            'OutputBucketName': self.bucket,
            'OutputKey': f"transcripts/{base_name}_transcript.json"
        }
        
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
    
    def extract_text(self, transcription_job):
        """Get transcript JSON from S3 and extract text"""
        try:
            job_name = transcription_job['TranscriptionJobName']
            
            # Try direct S3 access
            output_key = transcription_job.get('TranscriptionJob', {}).get('OutputKey')
            if output_key:
                json_s3_key = output_key
            else:
                json_s3_key = f"{job_name}.json"
            
            response = self.s3.get_object(Bucket=self.bucket, Key=json_s3_key)
            transcript_data = json.loads(response['Body'].read().decode('utf-8'))
            
            text = transcript_data['results']['transcripts'][0]['transcript']
            
            if not text.strip():
                text = "[No speech detected]"
            
            return text
            
        except Exception:
            # Search for transcript files
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
                    # Sort by most recent
                    json_files.sort(key=lambda x: self.s3.head_object(Bucket=self.bucket, Key=x)['LastModified'], reverse=True)
                    
                    for json_file in json_files:
                        try:
                            response = self.s3.get_object(Bucket=self.bucket, Key=json_file)
                            transcript_data = json.loads(response['Body'].read().decode('utf-8'))
                            
                            file_job_name = transcript_data.get('jobName', '')
                            if file_job_name == job_name or job_name.split('_')[1] in json_file:
                                text = transcript_data['results']['transcripts'][0]['transcript']
                                return text
                                
                        except Exception:
                            continue
                
                return None
                
            except Exception:
                return None
    
    def process_video(self, video_file):
        """MP4 TO TEXT: Upload → Transcribe → Extract Text"""
        try:
            # Upload to S3
            video_s3_key = self.upload_video(video_file)
            
            # Start transcription
            job_name = self.start_transcription(video_s3_key)
            
            # Wait for completion
            transcription_result = self.wait_for_transcription(job_name)
            
            if not transcription_result:
                return None
            
            # Extract text
            text = self.extract_text(transcription_result)
            
            return text
            
        except Exception:
            return None

def main():
    pipeline = MP4ToTextPipeline()
    
    # Find MP4 files
    mp4_files = [f for f in os.listdir('.') if f.endswith('.mp4')]
    
    if mp4_files:
        video_file = mp4_files[0]
        result = pipeline.process_video(video_file)
        
        if result:
            print(result)
        else:
            print("Failed to extract text")
    else:
        print("No MP4 files found")

if __name__ == "__main__":
    main()