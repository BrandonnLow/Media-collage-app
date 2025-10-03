from flask import Flask, render_template, request, redirect, url_for, jsonify
import os
from werkzeug.utils import secure_filename
import base64
from datetime import datetime
from urllib.parse import unquote
import subprocess
import tempfile
import math
from PIL import Image
import io

app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 100 * 1024 * 1024  # 100MB max file size
app.config['UPLOAD_FOLDER'] = 'static/videos'  # Keep same folder for backwards compatibility
app.config['MEDIA_PER_PAGE'] = 30  # Changed from VIDEOS_PER_PAGE to MEDIA_PER_PAGE

# Create necessary folders if they don't exist
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
os.makedirs('static/images', exist_ok=True)

def is_image_file(filename):
    """Check if file is an image"""
    return filename.lower().endswith(('.jpg', '.jpeg', '.png', '.gif', '.webp'))

def is_video_file(filename):
    """Check if file is a video"""
    return filename.lower().endswith(('.mp4', '.webm', '.ogg'))

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

def process_image(image_data):
    """Process and optimize image data"""
    try:
        # Decode base64 image
        image_binary = base64.b64decode(image_data)
        
        # Open image with PIL
        img = Image.open(io.BytesIO(image_binary))
        
        # Convert RGBA to RGB if necessary (for JPEG)
        if img.mode in ('RGBA', 'LA'):
            background = Image.new('RGB', img.size, (255, 255, 255))
            background.paste(img, mask=img.split()[-1] if img.mode == 'RGBA' else img.split()[1])
            img = background
        
        # Resize if too large (max 1920px on longest side)
        max_size = 1920
        if max(img.size) > max_size:
            img.thumbnail((max_size, max_size), Image.Resampling.LANCZOS)
        
        # Save to bytes
        output = io.BytesIO()
        img.save(output, format='JPEG', quality=90, optimize=True)
        return output.getvalue()
    except Exception as e:
        print(f"Image processing error: {str(e)}")
        return None

@app.route('/')
def index():
    """Grid view - Display videos and photos with pagination"""
    # Get page number from query parameter, default to 1
    page = request.args.get('page', 1, type=int)
    media_per_page = app.config['MEDIA_PER_PAGE']

    media_files = []
    media_folder = app.config['UPLOAD_FOLDER']

    # Get all media files (videos and images)
    if os.path.exists(media_folder):
        for filename in os.listdir(media_folder):
            if is_video_file(filename) or is_image_file(filename):
                file_path = os.path.join(media_folder, filename)
                media_files.append({
                    'filename': filename,
                    'type': 'image' if is_image_file(filename) else 'video',
                    'timestamp': os.path.getmtime(file_path)
                })

    # Sort by modification time (newest first)
    media_files.sort(key=lambda x: x['timestamp'], reverse=True)

    # Calculate pagination
    total_media = len(media_files)
    total_pages = math.ceil(total_media / media_per_page) if total_media > 0 else 1

    # Ensure page is within valid range
    if page < 1:
        page = 1
    elif page > total_pages:
        page = total_pages

    # Get media for current page
    start_idx = (page - 1) * media_per_page
    end_idx = start_idx + media_per_page
    page_media = media_files[start_idx:end_idx]

    # Prepare pagination info
    pagination_info = {
        'current_page': page,
        'total_pages': total_pages,
        'has_prev': page > 1,
        'has_next': page < total_pages,
        'prev_page': page - 1 if page > 1 else None,
        'next_page': page + 1 if page < total_pages else None,
        'total_media': total_media,
        'media_per_page': media_per_page,
        'start_idx': start_idx + 1 if total_media > 0 else 0,
        'end_idx': min(end_idx, total_media)
    }

    return render_template('index.html',
                         media_files=page_media,
                         pagination=pagination_info)

@app.route('/record')
def record():
    """Recording/capture screen"""
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

@app.route('/upload_photo', methods=['POST'])
def upload_photo():
    """Handle photo upload from capture"""
    try:
        data = request.json
        photo_data = data['photo']

        # Remove the data URL prefix
        photo_data = photo_data.split(',')[1]

        # Process and optimize the image
        processed_image = process_image(photo_data)
        
        if processed_image is None:
            # Fallback to raw image data if processing fails
            processed_image = base64.b64decode(photo_data)

        # Generate unique filename
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        photo_filename = f'photo_{timestamp}.jpg'
        photo_filepath = os.path.join(app.config['UPLOAD_FOLDER'], photo_filename)

        # Save the photo
        with open(photo_filepath, 'wb') as f:
            f.write(processed_image)

        return jsonify({'success': True, 'filename': photo_filename})

    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/delete/<path:filename>', methods=['DELETE'])
def delete_media(filename):
    """Delete a media file (video or photo)"""
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