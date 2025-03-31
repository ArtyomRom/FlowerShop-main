# Используем Python-образ
FROM python:3.10

# Устанавливаем рабочую директорию
WORKDIR /app

# Копируем файлы проекта
COPY . /app/

# Устанавливаем зависимости
RUN pip install --upgrade pip
RUN pip install -r requirements.txt

# Создаем папку для статических файлов, если её нет
RUN mkdir -p /app/staticfiles
RUN apt-get update && apt-get install -y supervisor

# Сборка статики
RUN python manage.py collectstatic --noinput

# Открываем порт
EXPOSE 8080

# Копируем конфигурацию supervisord
COPY supervisord.conf /etc/supervisor/conf.d/supervisord.conf

# Запускаем supervisord, чтобы он управлял процессами
CMD ["supervisord", "-c", "/etc/supervisor/conf.d/supervisord.conf"]
