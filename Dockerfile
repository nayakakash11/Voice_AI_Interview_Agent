version: '3.8'

services:
  # Service 1: The Brain (Python)
  backend:
    build: ./backend
    container_name: interview-backend
    ports:
      - "8000:8000"
    env_file:
      - ./backend/.env  # Point to your .env file inside backend
      - BACKEND_URL=${BACKEND_URL}
    volumes:
      # Persist the SQLite database so data survives restarts
      - ./backend/interview_state.db:/app/interview_state.db
    networks:
      - interview-net

  # Service 2: The Face (HTML/JS)
  frontend:
    build: ./frontend
    container_name: interview-frontend
    ports:
      - "3000:80" # We map port 3000 on your PC to port 80 in the container
    depends_on:
      - backend   # Wait for backend to start
    networks:
      - interview-net
    environment:
    - BACKEND_URL=${BACKEND_URL}  # Passes "http://192.168.1.50:8000" inside

networks:
  interview-net:
    driver: bridge