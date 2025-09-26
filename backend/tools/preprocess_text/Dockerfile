# Use the official AWS Lambda Python runtime base image
FROM public.ecr.aws/lambda/python:3.13

# Install system dependencies that PyMuPDF might need
# This is a good practice for libraries with C bindings
RUN dnf install -y freetype-devel gcc-c++ && dnf clean all

# Create a directory for the function code
WORKDIR ${LAMBDA_TASK_ROOT}

# Copy the requirements file and install dependencies
COPY requirements.txt .
RUN pip install -r requirements.txt

# Copy the function code
COPY app.py .

# Copy shared (layer) dependencies into /opt
COPY shared /opt/shared

# Set the CMD to your handler (filename.handler_function)
CMD [ "app.lambda_handler" ]
