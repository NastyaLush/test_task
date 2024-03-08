# Use an official Python runtime as a parent image
FROM joyzoursky/python-chromedriver:3.8

# Set the working directory in the container
WORKDIR /src
# Copy the current directory contents into the container at /usr/src/app

# Install the required packages
RUN pip install requests python-dotenv selenium beautifulsoup4 python-dateutil psycopg2
COPY . /src


CMD ["python", "script.py"]