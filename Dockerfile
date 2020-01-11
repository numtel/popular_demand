FROM python:3.6.6-alpine3.6
ENV PYTHONUNBUFFERED 1
RUN apk --update add \
  bash \
  freetype-dev \
  g++ \
  git \
  jpeg-dev \
  lcms2-dev \
  make \
  openjpeg-dev \
  openssh \
  postgresql-dev \
  tcl-dev \
  tiff-dev \
  tk-dev \
  zlib-dev \
  gettext \
  postgresql-client
WORKDIR /server
COPY ./requirements.txt /server
RUN pip install -r requirements.txt
COPY . /server
RUN python manage.py collectstatic
EXPOSE 8000
# ENTRYPOINT [ "python", "manage.py" ]
# CMD [ "runserver", \
#     "0.0.0.0:8000" ]
ENTRYPOINT [ "gunicorn" ]
CMD [ "-c", "gunicorn.conf.py", "popular_demand.wsgi" ]
