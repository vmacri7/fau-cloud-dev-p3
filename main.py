import os
import io
import json
import time
from flask import Flask, redirect, request, send_file, url_for, render_template_string
import google.generativeai as genai
from google.cloud import storage

storage_client = storage.Client()

BUCKET_NAME = "cloud-native-dev-p1"

# gemini api configuration
genai.configure(api_key=os.environ['GEMINI_API'])

# create upload directory if it doesn't exist
os.makedirs('uploads', exist_ok=True)

app = Flask(__name__)

# initialize gemini
def initialize_gemini_model():
    model = genai.GenerativeModel(
        model_name="gemini-1.5-flash",
    )
    return model

# analyze image with gemini ai
def analyze_image_with_gemini(image_path):
    model = initialize_gemini_model()
    
    # upload the file to gemini
    file = genai.upload_file(image_path, mime_type="image/jpeg")
    
    # prompt gemini to analyze the image
    prompt = "describe the image. provide a short title and a detailed description. return your response in json format with 'title' and 'description' fields."
    
    # get response from gemini
    response = model.generate_content([file, "\n\n", prompt])

    # strip '''json ... ''' which gemini adds to the response and any other invalid control characters
    json_text = response.text.replace("\n", " ").replace("\r", " ").replace("\t", " ").replace("```json", "").replace("```", "")

    try:
        result = json.loads(json_text)
    except json.JSONDecodeError as e:
        print("JSON PARSING ERROR:", e)
        print("FAILED JSON TEXT:", json_text)
        result = {
            "title": "error encountered in generating title",
            "description": "error encountered in generating description"
        }

    return result

# list file names in the bucket
def list_cloud_files(bucket_name=BUCKET_NAME):
    bucket = storage_client.bucket(bucket_name)
    blobs = bucket.list_blobs()
    files = []
    for blob in blobs:
        files.append(blob.name)
    return files
    
# uploads file to bucket in the cloud
def upload_file_to_cloud(file, bucket_name=BUCKET_NAME):
    bucket = storage_client.bucket(bucket_name)
    blob = bucket.blob(os.path.basename(file))
    
    # set appropriate content type for images
    content_type = "image/jpeg"
    blob.content_type = content_type
    
    # upload the file
    blob.upload_from_filename(file)
    
    return blob.name

# upload json metadata to cloud storage
def upload_json_to_cloud(json_data, filename, bucket_name=BUCKET_NAME):
    bucket = storage_client.bucket(bucket_name)
    json_filename = os.path.splitext(filename)[0] + ".json"
    blob = bucket.blob(json_filename)
    
    # Add timestamp to the JSON data for chronological ordering
    json_data["upload_timestamp"] = int(time.time())
    
    blob.upload_from_string(
        json.dumps(json_data),
        content_type="application/json"
    )
    
    return json_filename

# get json data from cloud storage
def get_json_from_cloud(json_filename, bucket_name=BUCKET_NAME):
    bucket = storage_client.bucket(bucket_name)
    blob = bucket.blob(json_filename)
    
    if not blob.exists():
        return {"title": "No metadata available", "description": "No description available", "upload_timestamp": 0}
    
    json_content = blob.download_as_string()
    return json.loads(json_content)

# get all images with their metadata
def get_all_images_with_metadata():
    image_data = []
    files = list_cloud_files()
    
    for file in files:
        if file.lower().endswith(".jpg") or file.lower().endswith(".jpeg"):
            # For each image, check if there's a corresponding JSON file
            json_filename = os.path.splitext(file)[0] + ".json"
            image_url = url_for('serve_file', filename=file)
            json_url = url_for('serve_json', filename=json_filename)
            
            # Get the metadata from the JSON file
            metadata = get_json_from_cloud(json_filename)
            
            image_data.append({
                "filename": file,
                "image_url": image_url,
                "json_url": json_url,
                "title": metadata.get("title", "No title available"),
                "description": metadata.get("description", "No description available"),
                "timestamp": metadata.get("upload_timestamp", 0)  # Default to 0 if not found
            })
    
    # Sort images by timestamp in descending order (newest first)
    image_data.sort(key=lambda x: x["timestamp"], reverse=True)
    
    return image_data

@app.route('/')
def index():
    # Get all images with their metadata
    images = get_all_images_with_metadata()
    
    html = """
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>AI Image Gallery</title>
        <link rel="stylesheet" href="/static/styles.css">
        <link rel="preconnect" href="https://fonts.googleapis.com">
        <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
        <link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap" rel="stylesheet">
    </head>
    <body>
        <div class="app-container">
            <header>
                <div class="header-content">
                    <h1>AI Image Gallery</h1>
                    <p>Upload images and let AI generate descriptions</p>
                </div>
            </header>
            
            <section class="upload-section">
                <form method="post" enctype="multipart/form-data" action="/upload" class="upload-form">
                    <div class="file-input-container">
                        <input type="file" id="file" name="form_file" accept="image/jpeg" class="file-input"/>
                        <label for="file" class="file-label">
                            <span class="file-icon">+</span>
                            <span class="file-text">Choose JPEG image</span>
                        </label>
                        <span class="selected-file-name"></span>
                    </div>
                    <button type="submit" class="upload-button">Upload & Analyze</button>
                </form>
            </section>
            
            <main class="gallery-section">
                <h2>Your Images</h2>
                <div class="image-grid">
    """
    
    # Add each image card to the HTML
    for image in images:
        # Truncate description if it's too long
        description = image['description']
            
        html += f"""
                    <div class="image-card">
                        <div class="image-container">
                            <img src="{image['image_url']}" alt="{image['title']}" loading="lazy">
                        </div>
                        <div class="image-info">
                            <h3 class="image-title">{image['title']}</h3>
                            <p class="image-description">{description}</p>
                            <div class="image-actions">
                                <a href="{image['image_url']}" target="_blank" class="action-button">View Image</a>
                                <a href="{image['json_url']}" target="_blank" class="action-button secondary">View JSON</a>
                            </div>
                        </div>
                    </div>
        """
    
    html += """
                </div>
            </main>
            
            <footer>
                <p>Vincenzo Macri · Cloud Native Dev · Project 3</p>
            </footer>
        </div>
        
        <script>
            // Show selected filename when a file is chosen
            document.querySelector('.file-input').addEventListener('change', function(e) {
                const fileName = e.target.files[0]?.name || 'No file selected';
                document.querySelector('.selected-file-name').textContent = fileName;
                document.querySelector('.file-label').classList.add('file-selected');
            });
            
            // Add animation to cards as they appear in viewport
            document.addEventListener('DOMContentLoaded', function() {
                const cards = document.querySelectorAll('.image-card');
                
                const observer = new IntersectionObserver((entries) => {
                    entries.forEach(entry => {
                        if (entry.isIntersecting) {
                            entry.target.classList.add('visible');
                            observer.unobserve(entry.target);
                        }
                    });
                }, { threshold: 0.1 });
                
                cards.forEach(card => {
                    observer.observe(card);
                });
            });
        </script>
    </body>
    </html>
    """
    
    return html

@app.route('/upload', methods=["POST"])
def upload():
    file = request.files['form_file']
    
    if file and (file.filename.lower().endswith('.jpg') or file.filename.lower().endswith('.jpeg')):
        # save file temporarily
        temp_path = os.path.join("./uploads", file.filename)
        file.save(temp_path)

        # analyze image using gemini
        image_data = analyze_image_with_gemini(temp_path)
        
        # upload image to cloud
        upload_file_to_cloud(temp_path)

        # upload json metadata to cloud (timestamp will be added by the function)
        upload_json_to_cloud(image_data, file.filename)
        
        # clean up temporary file
        os.remove(temp_path)

    return redirect(url_for('index'))

@app.route('/files')
def list_files():
    files = list_cloud_files()
    jpegs = []
    for file in files:
        if file.lower().endswith(".jpeg") or file.lower().endswith(".jpg"):
            jpegs.append(file)
    
    return jpegs

@app.route('/file/<filename>')
def serve_file(filename):
    bucket = storage_client.bucket(BUCKET_NAME)
    blob = bucket.blob(filename)
    
    # create a file-like object from the blob
    file_bytes = blob.download_as_bytes()
    byte_stream = io.BytesIO(file_bytes)
    
    content_type = 'image/jpeg'
    
    # serve the file
    return send_file(
        byte_stream,
        mimetype=content_type,
        as_attachment=False,
        download_name=filename
    )

@app.route('/json/<filename>')
def serve_json(filename):
    bucket = storage_client.bucket(BUCKET_NAME)
    blob = bucket.blob(filename)
    
    if not blob.exists():
        return {"error": "JSON file not found"}, 404
    
    # create a file-like object from the blob
    file_bytes = blob.download_as_bytes()
    byte_stream = io.BytesIO(file_bytes)
    
    content_type = 'application/json'
    
    # serve the file
    return send_file(
        byte_stream,
        mimetype=content_type,
        as_attachment=False,
        download_name=filename
    )

@app.route('/static/styles.css')
def serve_css():
    with open('static/styles.css', 'r') as file:
        css = file.read()
    
    return css, 200, {'Content-Type': 'text/css'}

if __name__ == '__main__':
    # Ensure static directory exists
    os.makedirs('static', exist_ok=True)
    
    app.run(debug=True)