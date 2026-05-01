<p align="center">
  <img src="assets/readme-header.png" alt="Veloretti bike" width="1200">
</p>

# Veloretti Home Assistant

Read-only Home Assistant integration for Veloretti e-bikes.

## Features

- UI login with the Veloretti magic email code flow.
- Vehicles appear as Home Assistant devices.
- GPS location through `device_tracker`.
- Dashboard-ready diagnostic model image entities, backed by the Veloretti model image when available.
- Odometer, VIN, vehicle status, SIM status, maintenance, warranty and firmware sensors.
- Configurable refresh interval from the integration options: 5, 10, 15 or 30 minutes.

## Installation with HACS

[![Open your Home Assistant instance and open this repository in HACS.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=NSURLSession0&repository=homeassistant-veloretti&category=integration)

1. Open this repository in HACS with the button above.
2. Install **Veloretti**.
3. Restart Home Assistant.
4. Go to **Settings > Devices & services > Add integration** and search for **Veloretti**.

## Dashboard image

Use the generated vehicle image entity in a picture entity card:

```yaml
type: picture-entity
entity: image.your_veloretti_vehicle_image
show_name: false
show_state: false
```

The downloaded image is also available from Home Assistant's local file server:

```yaml
type: picture
image: /local/veloretti/<vehicle_uuid>.png
```

## Privacy

The integration stores Veloretti tokens in the Home Assistant config entry so it can refresh the session. Tokens, account email and component serial numbers are not exposed as entity states or attributes. VIN is exposed intentionally as vehicle metadata and a diagnostic sensor.
