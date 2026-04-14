# Tahap 1: Build React App
FROM node:20 AS build
WORKDIR /app

# Konfigurasi build agar Vite mengerti ini jalan di Docker
ENV VITE_API_URL=/api
ENV GENERATE_SOURCEMAP=false
ENV CI=false
ENV DISABLE_ESLINT_PLUGIN=true
ENV NODE_OPTIONS="--max_old_space_size=4096"

COPY package*.json ./
RUN npm install --legacy-peer-deps

COPY . .
RUN npm run build

# Tahap 2: Serve dengan Nginx
FROM nginx:alpine
# Menghapus konfigurasi default nginx
RUN rm -rf /usr/share/nginx/html/*
# Menyalin hasil build dari tahap 1
COPY --from=build /app/build /usr/share/nginx/html
# Menyalin konfigurasi routing Nginx
COPY nginx-custom.conf /etc/nginx/conf.d/default.conf

EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]
