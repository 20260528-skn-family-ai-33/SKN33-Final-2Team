# GrowPath 화면 이미지: 1단계 node 로 빌드 → 2단계 nginx 가 빌드 결과(정적 파일)를 내고 /api 는 백엔드로 넘긴다.
# 최종 사용자는 브라우저만 있으면 된다(node·파이썬 필요 없음). 백엔드 주소는 실행할 때 API_UPSTREAM 으로 넣는다.
#   docker build -f frontend/Dockerfile -t growpath-web .  (저장소 루트에서)
#   docker run -p 8080:80 -e API_UPSTREAM=http://<백엔드 주소>:8785 growpath-web
FROM node:24-alpine AS build
WORKDIR /app/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ .
COPY VERSION /app/VERSION
# 시연 도구는 기본으로 숨긴다. 로컬 시연에서만 --build-arg VITE_DEMO_TOOLS=on과 서버 GP5_DEMO_MODE=on을 함께 설정한다.
ARG VITE_DEMO_TOOLS=off
ENV VITE_DEMO_TOOLS=$VITE_DEMO_TOOLS
RUN npm run build

FROM nginx:1.28-alpine
# nginx 공식 이미지는 시작할 때 templates/*.template 의 ${환경변수}를 채워 conf.d 에 둔다
ENV API_UPSTREAM=http://backend:8785
COPY frontend/nginx/default.conf.template /etc/nginx/templates/default.conf.template
COPY --from=build /app/frontend/dist /usr/share/nginx/html
EXPOSE 80
