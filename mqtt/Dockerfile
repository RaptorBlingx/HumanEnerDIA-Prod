# ============================================================================
# EnMS - MQTT Broker (Eclipse Mosquitto)
# Zero-touch deployment with auto-generated credentials
# ============================================================================

FROM eclipse-mosquitto:2.0

# Copy configuration
COPY config/mosquitto.conf /mosquitto/config/mosquitto.conf

# Create password file from deployment-provided credentials during build.
ARG MQTT_USERNAME
ARG MQTT_PASSWORD
RUN test -n "$MQTT_USERNAME" && test -n "$MQTT_PASSWORD" && \
    mosquitto_passwd -c -b /mosquitto/config/passwd "$MQTT_USERNAME" "$MQTT_PASSWORD" && \
    chown mosquitto:mosquitto /mosquitto/config/passwd && \
    chmod 600 /mosquitto/config/passwd

# Ensure proper ownership
RUN chown -R mosquitto:mosquitto /mosquitto/config

EXPOSE 1883 9001

CMD ["/usr/sbin/mosquitto", "-c", "/mosquitto/config/mosquitto.conf"]
