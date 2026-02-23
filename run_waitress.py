import os
from waitress import serve
from jobcard_system.wsgi import application

if __name__ == '__main__':
    print("Serving on http://0.0.0.0:8080")
    serve(application, host='0.0.0.0', port=8080)
