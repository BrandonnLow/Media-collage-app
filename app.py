from flask import Flask, render_template, request, redirect, url_for, jsonify
import os
from werkzeug.utils import secure_filename
import base64
from datetime import datetime

app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 100 * 1024 * 1024  # 100MB max file size
app.config['UPLOAD_FOLDER'] = 'static/videos'

# Create videos folder if it doesn't exist
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

@app.route('/')
def index():
    """Grid view - Display all videos"""
    videos = []
    video_folder = app.config['UPLOAD_FOLDER']
    
    # Get all video files
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
    try:
        data = request.json
        video_data = data['video']
        
        # Remove the data URL prefix
        video_data = video_data.split(',')[1]
        
        # Decode base64
        video_binary = base64.b64decode(video_data)
        
        # Generate unique filename
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f'video_{timestamp}.webm'
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        
        # Save the file
        with open(filepath, 'wb') as f:
            f.write(video_binary)
        
        return jsonify({'success': True, 'filename': filename})
    
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/delete/<filename>', methods=['DELETE'])
def delete_video(filename):
    """Delete a video file"""
    try:
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], secure_filename(filename))
        if os.path.exists(filepath):
            os.remove(filepath)
            return jsonify({'success': True})
        return jsonify({'success': False, 'error': 'File not found'}), 404
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)