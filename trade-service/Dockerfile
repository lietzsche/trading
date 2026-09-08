FROM maven:3.8.4 AS builder
COPY . .
RUN --mount=type=cache,target=/root/.m2 mvn clean package -DskipTests

FROM eclipse-temurin:17-jre
COPY --from=builder /target/trade-service-0.0.1-SNAPSHOT.jar app.jar
ENV ACTIVE=prd
ENV EUREKA_SERVER_URL=http://registry-server:8761/eureka/
ENV DB_URL=jdbc:postgresql://postgres_db:5432/postgres
EXPOSE 8080
ENTRYPOINT ["java", "-Dspring.profiles.active=${ACTIVE}", "-jar", "app.jar"]
