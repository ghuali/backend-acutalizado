from flask import Flask, request, jsonify
import psycopg2
import psycopg2.extras
import bcrypt
from flask_cors import CORS

app = Flask(__name__)
CORS(app)

# Conexión a PostgreSQL
def conectar():
    return psycopg2.connect(
        host="localhost",
        port="5432",
        database="EsportsCanarias",
        user="postgres",
        password="1234"
    )

# Ejecutar SQL y devolver JSON
def ejecutar_sql(sql, params=None):
    try:
        conn = conectar()
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        if params:
            cur.execute(sql, params)
        else:
            cur.execute(sql)

        if sql.strip().lower().startswith("select"):
            rows = cur.fetchall()
            cur.close()
            conn.close()
            return rows  # solo los datos sin jsonify aquí
        else:
            conn.commit()
            cur.close()
            conn.close()
            return {"msg": "Operación exitosa"}
    except Exception as e:
        return {"error": str(e)}


def ejecutar_sql_params(sql, params=None):
    try:
        conn = conectar()
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute(sql, params)

        if sql.strip().lower().startswith("select"):
            rows = cur.fetchall()
            cur.close()
            conn.close()
            return rows
        else:
            conn.commit()
            cur.close()
            conn.close()
            return None
    except Exception as e:
        print("Error ejecutar_sql:", e)
        raise e


@app.route('/usuario/login', methods=['POST'])
def login():
    data = request.json
    email = data['email']
    contraseña_plana = data['contraseña']

    resultado = ejecutar_sql('SELECT * FROM "Usuario" WHERE email = %s', (email,))
    if resultado:
        usuario = resultado[0]
        contraseña_hash = usuario['contraseña'].encode('utf-8')
        if bcrypt.checkpw(contraseña_plana.encode('utf-8'), contraseña_hash):

            user_data = {
                'id': usuario['id_usuario'],
                'nombre': usuario['nombre'],
                'email': usuario['email'],
                'rol': usuario['rol']
            }
            return jsonify(user_data)
    return jsonify({'error': 'Credenciales inválidas'}), 401


@app.route('/usuario/registro', methods=['POST'])
def registrar_usuario():
    data = request.json
    nombre = data['nombre']
    email = data['email']
    contraseña_plana = data['contraseña']
    rol = 'jugador'

    hashed = bcrypt.hashpw(contraseña_plana.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')

    sql = '''
        INSERT INTO "Usuario" (nombre, email, contraseña, rol)
        VALUES (%s, %s, %s, %s)
    '''
    ejecutar_sql(sql, (nombre, email, hashed, rol))
    return jsonify({'mensaje': 'Usuario registrado correctamente'})


@app.route('/equipo/crear', methods=['POST'])
def crear_equipo():
    data = request.json
    nombre = data['nombre']
    id_capitan = data['id_capitan']

    sql = 'INSERT INTO "Equipo" (nombre, id_capitan) VALUES (%s, %s)'
    ejecutar_sql(sql, (nombre, id_capitan))
    return jsonify({'mensaje': 'Equipo creado correctamente'})


@app.route('/torneo/crear', methods=['POST'])
def crear_torneo():
    data = request.json
    nombre = data['nombre']
    id_evento = data['id_evento']
    id_juego = data['id_juego']

    sql = 'INSERT INTO "Torneo" (nombre, id_evento, id_juego) VALUES (%s, %s, %s)'
    ejecutar_sql(sql, (nombre, id_evento, id_juego))
    return jsonify({'mensaje': 'Torneo creado correctamente'})


@app.route('/torneos', methods=['GET'])
def obtener_torneos():
    datos = ejecutar_sql('SELECT * FROM "Torneo"')
    return jsonify(datos)


@app.route('/eventos', methods=['GET'])
def obtener_eventos():
    datos = ejecutar_sql('SELECT * FROM "Evento"')
    return jsonify(datos)


@app.route('/juegos', methods=['GET'])
def obtener_juegos():
    datos = ejecutar_sql('SELECT * FROM "Juego"')
    return jsonify(datos)


@app.route('/clasificacion/<int:torneo_id>', methods=['GET'])
def clasificacion_torneo(torneo_id):
    datos = ejecutar_sql('''
        SELECT c.id_clasificacion, c.puntos, c.posicion,
               u.nombre AS usuario, eq.nombre AS equipo
        FROM "Clasificacion" c
        LEFT JOIN "Usuario" u ON c.id_usuario = u.id_usuario
        LEFT JOIN "Equipo" eq ON c.id_equipo = eq.id_equipo
        WHERE c.id_torneo = %s
        ORDER BY c.posicion ASC
    ''', (torneo_id,))
    return jsonify(datos)


@app.route('/torneo/<int:torneo_id>/equipos', methods=['GET'])
def equipos_en_torneo(torneo_id):
    datos = ejecutar_sql('''
        SELECT e.id_equipo, e.nombre
        FROM "Participa" p
        JOIN "Equipo" e ON p.id_equipo = e.id_equipo
        WHERE p.id_torneo = %s
    ''', (torneo_id,))
    return jsonify(datos)


@app.route('/torneo/<int:torneo_id>/jugadores', methods=['GET'])
def jugadores_en_torneo(torneo_id):
    datos = ejecutar_sql('''
        SELECT u.id_usuario, u.nombre
        FROM "Participa" p
        JOIN "Usuario" u ON p.id_usuario = u.id_usuario
        WHERE p.id_torneo = %s
    ''', (torneo_id,))
    return jsonify(datos)


@app.route('/torneo/<int:torneo_id>/partidas', methods=['GET'])
def partidas_en_torneo(torneo_id):
    datos = ejecutar_sql('''
        SELECT p.id_partida, p.fecha_hora, eq1.nombre AS equipo1, eq2.nombre AS equipo2, p.resultado
        FROM "Partida" p
        LEFT JOIN "Equipo" eq1 ON p.id_equipo1 = eq1.id_equipo
        LEFT JOIN "Equipo" eq2 ON p.id_equipo2 = eq2.id_equipo
        WHERE p.id_torneo = %s
        ORDER BY p.fecha_hora DESC
    ''', (torneo_id,))
    return jsonify(datos)


@app.route('/torneo/<int:torneo_id>/clasificacion', methods=['POST'])
def registrar_clasificacion(torneo_id):
    data = request.json
    puntos = data['puntos']
    posicion = data['posicion']
    id_usuario = data.get('id_usuario')
    id_equipo = data.get('id_equipo')

    sql = '''
        INSERT INTO "Clasificacion" (id_torneo, puntos, posicion, id_usuario, id_equipo)
        VALUES (%s, %s, %s, %s, %s)
    '''
    ejecutar_sql(sql, (torneo_id, puntos, posicion, id_usuario, id_equipo))
    return jsonify({'mensaje': 'Clasificación registrada correctamente'})


@app.route('/torneo/<int:torneo_id>/partida', methods=['POST'])
def registrar_partida(torneo_id):
    data = request.json
    fecha_hora = data['fecha_hora']
    id_equipo1 = data['id_equipo1']
    id_equipo2 = data['id_equipo2']
    resultado = data['resultado']

    sql = '''
        INSERT INTO "Partida" (id_torneo, fecha_hora, id_equipo1, id_equipo2, resultado)
        VALUES (%s, %s, %s, %s, %s)
    '''
    ejecutar_sql(sql, (torneo_id, fecha_hora, id_equipo1, id_equipo2, resultado))
    return jsonify({'mensaje': 'Partida registrada correctamente'})

if __name__ == '__main__':
    app.run(debug=True)