FROM python:3.11-slim

LABEL maintainer="vishnuvardhanreddy31"
LABEL description="QGenie Code Debugging Agent - Autonomous C/C++ bug detection"

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY agent.py .
COPY qgenie_sdk.py .
COPY scanner.py .
COPY analyzer.py .
COPY reporter.py .

ENTRYPOINT ["python", "agent.py"]
