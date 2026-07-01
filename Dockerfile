FROM python:3.10-slim

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
RUN pip install --no-cache-dir tzdata

# Copy source code
COPY src/ ./src/
COPY *.py ./

# Set environment variables
ENV PYTHONPATH=/app
ENV PYTHONUNBUFFERED=1
ENV TZ=Asia/Ho_Chi_Minh

# Expose port for the web server
EXPOSE 8000

# Default command (overridden by docker-compose for specific services)
CMD ["python", "src/web_server.py"]
