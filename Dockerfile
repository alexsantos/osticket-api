# Use the official Python 3.14 slim image for the amd64 architecture
FROM python:3.14-slim

# Set the working directory
WORKDIR /app

# Install uv, our package manager
RUN pip install uv

# Build dependencies for mysqlclient (a C extension linking against the MySQL client library)
RUN apt-get update && apt-get install -y --no-install-recommends \
    pkg-config \
    default-libmysqlclient-dev \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Copy dependency definitions
COPY pyproject.toml uv.lock ./

# Install exactly the versions pinned in uv.lock - the ones CI tested - verified by hash.
# --locked fails the build if uv.lock is out of date with pyproject.toml instead of re-resolving.
# The --system flag installs them in the global environment, which is common for containers
RUN uv export --locked --no-dev --no-emit-project -o /tmp/requirements.txt \
    && uv pip install --system --require-hashes -r /tmp/requirements.txt \
    && rm /tmp/requirements.txt

# Copy the rest of the application source code
COPY . .

# Expose the port the app runs on
# This will be whatever PORT is set to in the environment, defaulting to 8080
EXPOSE 8080

# Set the command to run the application
# This ensures our startup logic in main.py is always used
CMD ["python", "main.py"]
