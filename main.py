from flask import Flask, request, jsonify
import psycopg2
import psycopg2.extras
import bcrypt
from datetime import date
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
    id_fundador = data['id_capitan']  # nombre original del campo en frontend
    fecha_creacion = date.today()

    sql = 'INSERT INTO "Equipo" (nombre, fundador, fecha_creacion) VALUES (%s, %s, %s)'
    ejecutar_sql(sql, (nombre, id_fundador, fecha_creacion))
    return jsonify({'mensaje': 'Equipo creado correctamente'})


@app.route('/torneo/crear', methods=['POST'])
def crear_torneo():
    data = request.json
    nombre = data['nombre']
    fecha_inicio = data['fecha_inicio']
    fecha_fin = data['fecha_fin']
    ubicacion = data['ubicacion']
    id_evento = data['id_evento']
    id_juego = data['id_juego']

    sql = '''
        INSERT INTO "Torneo" (nombre, fecha_inicio, fecha_fin, ubicacion, id_evento, id_juego)
        VALUES (%s, %s, %s, %s, %s, %s)
    '''
    ejecutar_sql(sql, (nombre, fecha_inicio, fecha_fin, ubicacion, id_evento, id_juego))
    return jsonify({'mensaje': 'Torneo creado correctamente'})



@app.route('/torneos', methods=['GET'])
def obtener_torneos():
    datos = ejecutar_sql('SELECT * FROM "Torneo"')
    return jsonify(datos)


@app.route('/eventos', methods=['GET'])
def obtener_eventos():
    datos = ejecutar_sql('SELECT * FROM "Evento"')
    return jsonify(datos)


@app.route('/equipos', methods=['GET'])
def obtener_equipos():
    datos = ejecutar_sql('SELECT * FROM "Equipo"')
    return jsonify(datos)


@app.route('/equipos/por-juego/<int:id_juego>', methods=['GET'])
def obtener_equipos_por_juego(id_juego):
    sql = '''
        SELECT DISTINCT e.id_equipo, e.nombre
        FROM "Equipo" e
        JOIN "EquipoTorneo" et ON e.id_equipo = et.equipo_id
        JOIN "Torneo" t ON et.torneo_id = t.id_torneo
        WHERE t.id_juego = %s
    '''
    datos = ejecutar_sql(sql, (id_juego,))
    return jsonify(datos)


@app.route('/juegos', methods=['GET'])
def obtener_juegos():
    tipo = request.args.get('tipo')  # puede ser 'equipo' o 'individual'
    if tipo == 'equipo':
        datos = ejecutar_sql('SELECT * FROM "Juego" WHERE es_individual = FALSE')
    elif tipo == 'individual':
        datos = ejecutar_sql('SELECT * FROM "Juego" WHERE es_individual = TRUE')
    else:
        datos = ejecutar_sql('SELECT * FROM "Juego"')  # sin filtro
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
        FROM "EquipoTorneo" et
        JOIN "Equipo" e ON et.equipo_id = e.id_equipo
        WHERE et.torneo_id = %s
    ''', (torneo_id,))
    return jsonify(datos)

@app.route('/torneo/<int:torneo_id>/jugadores', methods=['GET'])
def jugadores_en_torneo(torneo_id):
    datos = ejecutar_sql('''
        SELECT u.id_usuario, u.nombre
        FROM "UsuarioTorneo" ut
        JOIN "Usuario" u ON ut.usuario_id = u.id_usuario
        WHERE ut.torneo_id = %s
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

if __name__ == '__main__':
    app.run(debug=True)