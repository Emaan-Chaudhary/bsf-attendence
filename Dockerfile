# ✅ Base image
FROM python:3.13

# ✅ Set working directory
WORKDIR /app

# ✅ Copy project files
COPY . .

# ✅ Install dependencies
RUN pip install --no-cache-dir -r requirements.txt \
    && pip install gunicorn

# ✅ Expose port
EXPOSE 5000

# ✅ Run Gunicorn server
CMD ["gunicorn", "--bind", "0.0.0.0:5000", "server:app"]

