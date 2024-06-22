from flask import Flask, request, send_file, render_template, jsonify, send_from_directory
from werkzeug.utils import secure_filename
from pydub import AudioSegment
from PIL import Image, UnidentifiedImageError
from moviepy.editor import VideoFileClip
from pdf2image import convert_from_path
from apscheduler.schedulers.background import BackgroundScheduler
import os
import zipfile
import time
import json

app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = 'uploads'
app.config['CONVERTED_FOLDER'] = 'converted'
app.config['COMPRESSED_FOLDER'] = 'compressed'
app.config['TEMP_FILE_LIFETIME'] = 3600  # 60 minutes
app.config['MAX_FILE_SIZE'] = 100 * 1024 * 1024  # 100MB in bytes

if not os.path.exists(app.config['UPLOAD_FOLDER']):
    os.makedirs(app.config['UPLOAD_FOLDER'])
if not os.path.exists(app.config['CONVERTED_FOLDER']):
    os.makedirs(app.config['CONVERTED_FOLDER'])
if not os.path.exists(app.config['COMPRESSED_FOLDER']):
    os.makedirs(app.config['COMPRESSED_FOLDER'])

counters = {
    'total_conversions': 0,
    'total_compressions': 0
}

def load_counters():
    global counters
    if os.path.exists('counters.json'):
        with open('counters.json', 'r') as f:
            counters = json.load(f)

def save_counters():
    with open('counters.json', 'w') as f:
        json.dump(counters, f)

load_counters()

def cleanup_temp_files():
    now = time.time()
    for folder in [app.config['UPLOAD_FOLDER'], app.config['CONVERTED_FOLDER'], app.config['COMPRESSED_FOLDER']]:
        for filename in os.listdir(folder):
            file_path = os.path.join(folder, filename)
            if os.path.getmtime(file_path) < now - app.config['TEMP_FILE_LIFETIME']:
                os.remove(file_path)
                print(f'Deleted temporary file: {file_path}')

def start_scheduler():
    scheduler = BackgroundScheduler()
    scheduler.add_job(func=cleanup_temp_files, trigger="interval", minutes=10)
    scheduler.start()

@app.route('/static/<path:filename>')
def static_files(filename):
    return send_from_directory('static', filename)

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/upload_and_convert', methods=['POST'])
def upload_and_convert():
    if 'files' not in request.files:
        return 'No file part', 400
    files = request.files.getlist('files')
    if len(files) == 0:
        return 'No selected files', 400

    allowed_file_types = ['image/jpeg', 'image/png', 'application/pdf', 'video/mp4', 'video/webm', 'video/x-matroska', 'video/quicktime', 'audio/mpeg']
    for file in files:
        if file.mimetype not in allowed_file_types:
            return 'Unsupported file type for the file converter.', 400
        if file.content_length > app.config['MAX_FILE_SIZE']:
            return 'File exceeds the maximum file size of 100MB.', 400

    output_formats = [request.form[f'format_{i}'] for i in range(len(files))]
    converted_files = []
    now = time.time()

    try:
        for file, output_format in zip(files, output_formats):
            original_filename = file.filename
            filename = secure_filename(original_filename)
            input_file = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            file.save(input_file)
            output_file = os.path.join(app.config['CONVERTED_FOLDER'], f'converted_{filename.rsplit(".", 1)[0]}.{output_format}')
            file_type = file.mimetype

            if file_type.startswith('audio/'):
                audio = AudioSegment.from_file(input_file)
                audio.export(output_file, format=output_format)
                converted_files.append(output_file)
            elif file_type.startswith('image/'):
                image = Image.open(input_file)
                if output_format.lower() == 'jpeg' and image.mode != 'RGB':
                    image = image.convert('RGB')
                image.save(output_file, format=output_format.upper())
                converted_files.append(output_file)
            elif file_type.startswith('video/') or file.filename.lower().endswith(('webm', 'mkv', 'mov')):
                video = VideoFileClip(input_file)
                video.write_videofile(output_file, codec='libx264' if output_format == 'mp4' else 'libvpx' if output_format == 'webm' else 'libx265')
                converted_files.append(output_file)
            elif file_type == 'application/pdf':
                try:
                    images = convert_from_path(input_file)
                    if output_format.lower() in ['jpeg', 'png']:
                        for i, img in enumerate(images):
                            img_output_file = os.path.join(app.config['CONVERTED_FOLDER'], f'{filename.rsplit(".", 1)[0]}_page_{i + 1}.{output_format}')
                            img.save(img_output_file, format=output_format.upper())
                            converted_files.append(img_output_file)
                    else:
                        return 'Unsupported conversion format for PDF', 400
                except Exception as e:
                    print(f'Error converting PDF: {e}')
                    return 'Error converting PDF. Ensure poppler is installed and in PATH.', 500
            else:
                return 'Unsupported file type', 400

        counters['total_conversions'] += len(files)
        save_counters()

        if len(converted_files) == 1:
            return send_file(converted_files[0], as_attachment=True)
        else:
            zip_filename = 'converted_files.zip'
            zip_filepath = os.path.join(app.config['CONVERTED_FOLDER'], zip_filename)
            with zipfile.ZipFile(zip_filepath, 'w') as zipf:
                for file in converted_files:
                    zipf.write(file, os.path.basename(file))
            return send_file(zip_filepath, as_attachment=True)

    except UnidentifiedImageError:
        return 'One or more files could not be identified as valid images.', 400
    except Exception as e:
        print(f'Error converting file(s): {e}')
        return f'Error converting file(s): {e}', 500

@app.route('/compress_image', methods=['POST'])
def compress_image():
    if 'image' not in request.files or 'quality' not in request.form:
        return 'No image or quality provided', 400

    image = request.files['image']
    if image.mimetype not in ['image/jpeg', 'image/png']:
        return 'Unsupported file type for the image compressor.', 400
    if image.content_length > app.config['MAX_FILE_SIZE']:
        return 'File exceeds the maximum file size of 100MB.', 400

    quality = int(request.form['quality'])
    original_filename = image.filename
    filename = secure_filename(original_filename)
    input_file = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    image.save(input_file)
    now = time.time()

    try:
        img = Image.open(input_file)
        output_file = os.path.join(app.config['COMPRESSED_FOLDER'], f'compressed_{filename}')
        img.save(output_file, optimize=True, quality=quality)

        counters['total_compressions'] += 1
        save_counters()

        return send_file(output_file, as_attachment=True)
    except UnidentifiedImageError:
        return 'The provided file could not be identified as a valid image.', 400
    except Exception as e:
        print(f'Error compressing image: {e}')
        return f'Error compressing image: {e}', 500

@app.route('/get_counters', methods=['GET'])
def get_counters():
    return jsonify(counters)

if __name__ == '__main__':
    start_scheduler()
    app.run(debug=True, host='0.0.0.0')
