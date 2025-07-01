echo FROM python:3.10.13-slim-bookworm > Dockerfile
echo WORKDIR /app >> Dockerfile
echo COPY requirements.txt . >> Dockerfile
echo RUN pip install --upgrade pip && pip install -r requirements.txt >> Dockerfile
echo COPY . . >> Dockerfile
echo CMD ["python", "bk.py"] >> Dockerfile