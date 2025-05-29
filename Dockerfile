# Use official Python image
FROM python:3.10-slim

# Set working directory
WORKDIR /app

# Copy all project files into the container
COPY . /app

# Install dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Set environment variable for production
ENV PYTHONUNBUFFERED=1

# Run the bot
CMD ["python", "main.py"]
