from flask import Flask, render_template, request, redirect, url_for, jsonify
import os
from werkzeug.utils import secure_filename
import base64
from datetime import datetime
from urllib.parse import unquote
import subprocess
import tempfile

app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 100 * 1024 * 1024  # 100MB max file size
app.config['UPLOAD_FOLDER'] = 'static/videos'

# Create necessary folders if they don't exist
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
os.makedirs('static/images', exist_ok=True)

def convert_webm_to_mp4(webm_path, mp4_path):
    """Convert WebM video to MP4 using ffmpeg"""
    try:
        # ffmpeg command for conversion
        cmd = [
            'ffmpeg',
            '-i', webm_path,  # Input file
            '-c:v', 'libx264',  # Video codec
            '-preset', 'fast',  # Encoding speed/quality trade-off
            '-crf', '22',  # Quality (lower = better, 0-51)
            '-c:a', 'aac',  # Audio codec
            '-b:a', '128k',  # Audio bitrate
            '-movflags', '+faststart',  # Optimize for web streaming
            '-y',  # Overwrite output file
            mp4_path  # Output file
        ]
        
        # Run ffmpeg
        result = subprocess.run(cmd, capture_output=True, text=True)
        
        if result.returncode != 0:
            print(f"FFmpeg error: {result.stderr}")
            return False
            
        return True
    except Exception as e:
        print(f"Conversion error: {str(e)}")
        return False

@app.route('/')
def index():
    """Grid view - Display all videos"""
    videos = []
    video_folder = app.config['UPLOAD_FOLDER']

    # Get all video files (now looking for MP4 files)
    if os.path.exists(video_folder):
        for filename in os.listdir(video_folder):
            if filename.endswith(('.mp4', '.webm', '.ogg')):
                videos.append(filename)

    # Sort by modification time (newest first)
    videos.sort(key=lambda x: os.path.getmtime(os.path.join(video_folder, x)), reverse=True)

    return render_template('index.html', videos=videos)

@app.route('/record')
def record():
    """Recording screen"""
    return render_template('record.html')

@app.route('/upload', methods=['POST'])
def upload_video():
    """Handle video upload from recording"""
    temp_webm_path = None
    try:
        data = request.json
        video_data = data['video']

        # Remove the data URL prefix
        video_data = video_data.split(',')[1]

        # Decode base64
        video_binary = base64.b64decode(video_data)

        # Generate unique filename
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        
        # Create a temporary WebM file
        temp_webm_fd, temp_webm_path = tempfile.mkstemp(suffix='.webm')
        os.close(temp_webm_fd)  # Close the file descriptor
        
        # Save the WebM file temporarily
        with open(temp_webm_path, 'wb') as f:
            f.write(video_binary)

        # Final MP4 filename and path
        mp4_filename = f'video_{timestamp}.mp4'
        mp4_filepath = os.path.join(app.config['UPLOAD_FOLDER'], mp4_filename)

        # Convert WebM to MP4
        if convert_webm_to_mp4(temp_webm_path, mp4_filepath):
            # Clean up temporary WebM file
            if os.path.exists(temp_webm_path):
                os.remove(temp_webm_path)
            
            return jsonify({'success': True, 'filename': mp4_filename})
        else:
            # If conversion fails, save as WebM as fallback
            webm_filename = f'video_{timestamp}.webm'
            webm_filepath = os.path.join(app.config['UPLOAD_FOLDER'], webm_filename)
            
            with open(webm_filepath, 'wb') as f:
                f.write(video_binary)
            
            # Clean up temporary file
            if os.path.exists(temp_webm_path):
                os.remove(temp_webm_path)
                
            return jsonify({
                'success': True, 
                'filename': webm_filename,
                'warning': 'MP4 conversion failed, saved as WebM'
            })

    except Exception as e:
        # Clean up temporary file on error
        if temp_webm_path and os.path.exists(temp_webm_path):
            os.remove(temp_webm_path)
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/delete/<path:filename>', methods=['DELETE'])
def delete_video(filename):
    """Delete a video file"""
    try:
        # URL decode the filename to handle spaces and special characters
        filename = unquote(filename)

        # Construct the filepath
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)

        # Check if file exists and delete it
        if os.path.exists(filepath):
            os.remove(filepath)
            return jsonify({'success': True})

        # If not found, try with secure_filename (for backwards compatibility)
        secure_filepath = os.path.join(app.config['UPLOAD_FOLDER'], secure_filename(filename))
        if os.path.exists(secure_filepath):
            os.remove(secure_filepath)
            return jsonify({'success': True})

        return jsonify({'success': False, 'error': 'File not found'}), 404
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)