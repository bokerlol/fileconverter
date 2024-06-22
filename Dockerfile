# Use the official Python image from the Docker Hub
FROM python:3.9-slim

# Set environment variables to prevent Python from writing pyc files and buffer stdout and stderr
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

# Install system dependencies, poppler-utils, and ffmpeg
RUN apt-get update && apt-get install -y \
    gcc \
    libmagic1 \
    poppler-utils \
    ffmpeg \
    git \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Set the working directory inside the container
WORKDIR /app

# Clone the repository (replace with your repository URL)
RUN git clone https://github.com/bokerlol/fileconverter .

# Install the dependencies specified in requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Copy the entire application directory into the working directory
COPY . .

# Expose the port the application runs on
EXPOSE 5000

# Command to run the Flask application
CMD ["python", "app.py"]
