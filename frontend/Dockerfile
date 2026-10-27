# GrowPath 화면 이미지: 1단계 node 로 빌드 → 2단계 nginx 가 빌드 결과(정적 파일)를 내고 /api 는 백엔드로 넘긴다.
# 최종 사용자는 브라우저만 있으면 된다(node·파이썬 필요 없음). 백엔드 주소는 실행할 때 API_UPSTREAM 으로 넣는다.
#   docker build -t growpath-web ./frontend
#   docker run -p 8080:80 -e API_UPSTREAM=http://<백엔드 주소>:8785 growpath-web
FROM node:24-alpine AS build
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY . .
# 시연 도구(좌측 메뉴의 단계 이동·실패 시험) 표시. 실제 배포에서는 --build-arg VITE_DEMO_TOOLS=off
ARG VITE_DEMO_TOOLS=on
ENV VITE_DEMO_TOOLS=$VITE_DEMO_TOOLS
RUN npm run build

FROM nginx:1.28-alpine
# nginx 공식 이미지는 시작할 때 templates/*.template 의 ${환경변수}를 채워 conf.d 에 둔다
ENV API_UPSTREAM=http://backend:8785
COPY nginx/default.conf.template /etc/nginx/templates/default.conf.template
COPY --from=build /app/dist /usr/share/nginx/html
EXPOSE 80
