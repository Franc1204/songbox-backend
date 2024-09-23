# SongBox Backend

Este es el backend de la aplicación **SongBox**, que permite a los usuarios compartir opiniones sobre canciones, álbumes y playlists usando la API de Spotify.

## Requisitos

- **Python 3.8+**
- **MongoDB** (Para la base de datos)
- **Spotify Developer Account** (Para obtener las credenciales de la API de Spotify)

## Instalación

1. Clona este repositorio:
   ```bash
   git clone https://github.com/tu_usuario/songbox-backend.git


# Notas importantes

1. Antes de usar la API de Spotify, debes iniciar sesión en Spotify a través de la ruta:

```
http://127.0.0.1:5000/
```
Esto es necesario para autenticar tu sesión con Spotify.

2. Si eres un nuevo usuario, primero regístrate usando la ruta:

```
http://127.0.0.1:5000/register
```
O inicia sesión usando la ruta:

```
http://127.0.0.1:5000/login
```

3. Redireccionamiento pendiente: Actualmente, el redireccionamiento tras iniciar sesión en Spotify no está implementado. Por lo tanto, es importante acceder manualmente a http://127.0.0.1:5000/ para iniciar sesión en Spotify.