FROM maven:3.8.4 AS builder
COPY . .
RUN mvn clean package -DskipTests

FROM eclipse-temurin:17-jre
COPY --from=builder /target/admin-server-0.0.1-SNAPSHOT.jar app.jar
ENV EUREKA_SERVER_URL=http://registry-server:8761/eureka/
EXPOSE 9090
ENTRYPOINT ["java", "-jar", "app.jar"]
