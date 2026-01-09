FROM node:18-alpine
WORKDIR /usr/src/app
ARG NEXT_PUBLIC_API_BASE
ENV NEXT_PUBLIC_API_BASE=$NEXT_PUBLIC_API_BASE
COPY package.json ./
RUN npm install --production=false
COPY . .
RUN npm run build
EXPOSE 3000
CMD ["npm", "run", "start"]
