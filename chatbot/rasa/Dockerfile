# Rasa NLU Server Dockerfile
# Uses official Rasa image with pre-trained model
FROM rasa/rasa:3.6.21

WORKDIR /app

# Copy pre-trained model
COPY models/ /app/models/

# Copy endpoints configuration
COPY endpoints.yml /app/endpoints.yml

# Expose Rasa port
EXPOSE 5005

# Run Rasa server with API enabled and endpoints config
CMD ["run", "--enable-api", "--cors", "*", "--port", "5005", "--endpoints", "endpoints.yml"]
