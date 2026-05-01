# Changelog

## 0.2.0

- Added VIN as vehicle serial number and diagnostic sensor.
- Added diagnostic model image entities for dashboard use.
- Downloaded Veloretti model images to the local Home Assistant cache.
- Kept device trackers on the standard bicycle icon instead of using model images.
- Added a configurable refresh interval with 5, 10, 15 and 30 minute choices.
- Added a timeout for optional model image downloads so setup can continue when the signed image URL is slow or unavailable.
- Prevented refreshed token storage from reloading the integration during setup or polling.

## 0.1.0

- Initial read-only Veloretti integration.
- Added UI login, token refresh, vehicle devices, location, status, maintenance, warranty and firmware entities.
