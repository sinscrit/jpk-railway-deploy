#!/usr/bin/env python3
import requests
import json
import hashlib
import time
import os

class ConversionTester:
    def __init__(self, railway_url, local_url=None):
        self.railway_url = railway_url
        self.local_url = local_url or "http://localhost:8000"
        
    def test_conversion_parity(self, test_file_path):
        """Test conversion parity between Railway and local"""
        results = {
            'test_file': test_file_path,
            'timestamp': time.time(),
            'railway': {},
            'local': {},
            'comparison': {}
        }
        
        # Test Railway conversion
        print(f"🚀 Testing Railway conversion: {test_file_path}")
        railway_result = self._test_single_conversion(self.railway_url, test_file_path)
        results['railway'] = railway_result
        
        # Test local conversion (if available)
        if self.local_url:
            print(f"🏠 Testing local conversion: {test_file_path}")
            local_result = self._test_single_conversion(self.local_url, test_file_path)
            results['local'] = local_result
            
            # Compare results
            results['comparison'] = self._compare_results(railway_result, local_result)
        
        return results
    
    def _test_single_conversion(self, base_url, file_path):
        """Test conversion on a single endpoint"""
        start_time = time.time()
        
        try:
            # Upload file
            with open(file_path, 'rb') as f:
                files = {'file': f}
                upload_response = requests.post(f"{base_url}/api/converter/upload", files=files)
            
            if upload_response.status_code != 200:
                return {'error': f'Upload failed: {upload_response.status_code}', 'processing_time': 0}
            
            job_id = upload_response.json()['job_id']
            
            # Poll for completion
            max_wait = 300  # 5 minutes
            poll_start = time.time()
            
            while time.time() - poll_start < max_wait:
                status_response = requests.get(f"{base_url}/api/converter/status/{job_id}")
                if status_response.status_code != 200:
                    return {'error': f'Status check failed: {status_response.status_code}', 'processing_time': 0}
                
                status_data = status_response.json()
                
                if status_data['status'] == 'completed':
                    # Download result
                    download_response = requests.get(f"{base_url}/api/converter/download/{job_id}")
                    if download_response.status_code == 200:
                        output_size = len(download_response.content)
                        processing_time = time.time() - start_time
                        
                        # Calculate content hash for comparison
                        content_hash = hashlib.md5(download_response.content).hexdigest()
                        
                        return {
                            'success': True,
                            'output_size': output_size,
                            'processing_time': processing_time,
                            'content_hash': content_hash,
                            'job_id': job_id
                        }
                    else:
                        return {'error': f'Download failed: {download_response.status_code}', 'processing_time': time.time() - start_time}
                
                elif status_data['status'] == 'error':
                    return {'error': f'Conversion failed: {status_data.get("message", "Unknown error")}', 'processing_time': time.time() - start_time}
                
                time.sleep(2)  # Wait 2 seconds before next poll
            
            return {'error': 'Conversion timeout', 'processing_time': time.time() - start_time}
            
        except Exception as e:
            return {'error': f'Test exception: {str(e)}', 'processing_time': time.time() - start_time}
    
    def _compare_results(self, railway_result, local_result):
        """Compare Railway vs local conversion results"""
        comparison = {}
        
        if railway_result.get('success') and local_result.get('success'):
            # Size comparison
            railway_size = railway_result['output_size']
            local_size = local_result['output_size']
            size_ratio = railway_size / local_size if local_size > 0 else 0
            
            comparison['size_match'] = abs(size_ratio - 1.0) < 0.05  # Within 5%
            comparison['size_ratio'] = size_ratio
            comparison['size_difference_mb'] = (railway_size - local_size) / (1024*1024)
            
            # Time comparison
            railway_time = railway_result['processing_time']
            local_time = local_result['processing_time']
            time_ratio = railway_time / local_time if local_time > 0 else 0
            
            comparison['time_reasonable'] = 0.5 <= time_ratio <= 2.0  # Within 2x
            comparison['time_ratio'] = time_ratio
            comparison['time_difference_s'] = railway_time - local_time
            
            # Content comparison
            comparison['content_identical'] = railway_result['content_hash'] == local_result['content_hash']
            
            # Overall assessment
            comparison['overall_pass'] = (
                comparison['size_match'] and 
                comparison['time_reasonable'] and 
                comparison['content_identical']
            )
        else:
            comparison['overall_pass'] = False
            comparison['railway_success'] = railway_result.get('success', False)
            comparison['local_success'] = local_result.get('success', False)
        
        return comparison

# Usage example
if __name__ == "__main__":
    import sys
    
    railway_url = "https://jbjpk2json-production.up.railway.app"
    local_url = "http://localhost:8000" if len(sys.argv) < 2 else sys.argv[1]
    
    tester = ConversionTester(railway_url, local_url)
    results = tester.test_conversion_parity("baseline/original_source_vb.jpk")
    
    print(json.dumps(results, indent=2))
    
    if results.get('comparison', {}).get('overall_pass'):
        print("✅ CONVERSION PARITY TEST PASSED")
        exit(0)
    else:
        print("❌ CONVERSION PARITY TEST FAILED")
        exit(1)
