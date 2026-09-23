FROM node:24-alpine

RUN apk add --no-cache curl zip

WORKDIR /app

COPY frontend/package.json /app/frontend/package.json
RUN cd /app/frontend && npm install

COPY frontend /app/frontend
COPY netlify-uploader/upload.sh /app/upload.sh

ENV VITE_API_URL=https://api-production-4632.up.railway.app
ENV VITE_WS_URL=wss://api-production-4632.up.railway.app

RUN cd /app/frontend && npm run build
RUN chmod +x /app/upload.sh

CMD ["/app/upload.sh"]
