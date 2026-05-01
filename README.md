<p align="center">
  <img src="assets/readme-header.png" alt="Veloretti bike" width="1200">
</p>

# Veloretti Home Assistant

Read-only Home Assistant integration for Veloretti vehicles.

## Features

- UI login with the Veloretti magic email code flow.
- Vehicles appear as Home Assistant devices.
- GPS location through `device_tracker`.
- Odometer, vehicle status, SIM status, maintenance, warranty and firmware sensors.
- Access tokens are refreshed with Veloretti's `/v3/auth/refresh` endpoint.

## Installation with HACS

1. Add this repository as a custom integration repository in HACS.
2. Install **Veloretti**.
3. Restart Home Assistant.
4. Go to **Settings > Devices & services > Add integration** and search for **Veloretti**.

## Privacy

The integration stores Veloretti tokens in the Home Assistant config entry so it can refresh the session. Tokens, account email, VINs and component serial numbers are not exposed as entity states or attributes.
