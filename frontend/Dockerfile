# Imagen de desarrollo: servidor de Vite con recarga automática.
# (Para producción se agregará una etapa con nginx que sirva los archivos compilados.)
FROM node:22

WORKDIR /app

COPY package*.json ./
RUN npm install

COPY . .

EXPOSE 5173

CMD ["npm", "run", "dev"]
