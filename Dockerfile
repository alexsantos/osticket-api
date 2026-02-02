# Use the official Python 3.14 slim image for the amd64 architecture
FROM --platform=linux/amd64 python:3.14-slim

# Set the working directory
WORKDIR /app

# Install uv, our package manager
RUN pip install uv

# Copy dependency definitions
COPY pyproject.toml uv.lock* ./

# Install dependencies using uv
# The --system flag installs them in the global environment, which is common for containers
RUN uv pip install --system -r pyproject.toml

# Copy the rest of the application source code
COPY . .

# Expose the port the app runs on
# This will be whatever PORT is set to in the environment, defaulting to 8080
EXPOSE 8080

# Set the command to run the application
# This ensures our startup logic in main.py is always used
CMD ["python", "main.py"]
