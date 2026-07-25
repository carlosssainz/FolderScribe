# FolderScribe — Visión del producto

## 1. Problema que resuelve

Las carpetas de descargas, documentos y proyectos acumulan archivos sin
organización. El usuario termina con decenas o cientos de archivos cuyo nombre
no refleja su contenido, mezclando tipos, formatos y propósitos. Ordenar
manualmente es tedioso, propenso a errores y difícil de mantener.

FolderScribe automatiza el análisis, la propuesta de organización y el
renombrado, manteniendo al usuario en control en cada paso.

## 2. Visión del producto

FolderScribe es un organizador físico e inteligente de archivos para Ubuntu
24.04. Analiza el contenido de una carpeta, propone una estructura de
clasificación, explica sus decisiones, solicita aprobación y ejecuta los
cambios de forma reversible.

El usuario no pierde visibilidad ni control en ningún momento: cada movimiento
y cada renombrado deben ser aprobados explícitamente antes de ejecutarse.

## 3. Usuario inicial

Usuarios de Ubuntu 24.04 que quieren organizar su carpeta de Descargas sin
invertir horas ni arriesgarse a perder archivos. A medio plazo, cualquier
usuario que necesite poner orden en directorios con mezcla de formatos.

## 4. Principios

- **Control del usuario.** Cada movimiento o renombrado requiere aprobación
  explícita. El usuario puede corregir, ajustar, crear carpetas y omitir
  archivos.
- **Ninguna modificación durante el análisis.** FolderScribe solo lee. No crea,
  mueve ni renombra nada hasta que el usuario lo ordena.
- **Transparencia.** Toda decisión automática se explica: por qué un archivo va
  a una carpeta y no a otra, y con qué nivel de confianza.
- **Privacidad.** El usuario decide qué información sale de su equipo y cuál se
  procesa exclusivamente en local.
- **Reversibilidad.** Toda operación se registra y puede deshacerse.
- **Una única ubicación física por archivo.** No se duplican archivos en el
  sistema de archivos.
- **Varias etiquetas en el índice local.** Un archivo puede pertenecer a varias
  categorías lógicas aunque solo esté en un sitio físico.

## 5. Flujo general

1. **Seleccionar carpeta** — El usuario elige el directorio a organizar.
2. **Inventariar** — Se listan todos los archivos, respetando exclusiones y
   límites de seguridad.
3. **Analizar** — Se extraen metadatos, texto y tipo MIME. Se detectan
   duplicados, formatos no soportados y proyectos de código.
4. **Proponer** — FolderScribe sugiere una clasificación (carpetas) y un
   renombrado, con explicación y nivel de confianza para cada archivo.
5. **Revisar** — El usuario ve el árbol actual y el propuesto, y puede aprobar
   por archivo, por grupo, corregir destinos, crear carpetas o excluir
   archivos.
6. **Aprobar** — Confirmación final de los cambios pendientes.
7. **Ejecutar** — Se mueven y renombran los archivos según lo aprobado.
8. **Registrar** — Cada operación queda en el historial local.
9. **Deshacer si es necesario** — FolderScribe puede revertir una operación
   ejecutada, restaurando la ubicación y el nombre original.

## 6. Capacidades futuras

- **Renombrado inteligente.** Nombres descriptivos basados en contenido,
  fecha y metadatos.
- **Duplicados exactos.** Detección por hash y fusión en una única copia
  física.
- **Documentos similares.** Agrupación de archivos con contenido parecido
  (versiones, borradores).
- **OCR.** Extracción de texto en PDF escaneados, con modo rápido y modo
  completo.
- **Índice local.** Base de datos que permite búsqueda y etiquetado sin
  depender de la estructura de carpetas.
- **Árbol actual y árbol propuesto.** Vista comparativa antes de ejecutar.
- **Plantillas configurables.** Reglas de organización guardadas y reutilizables
  por el usuario.
- **Reglas aprendidas con aprobación.** FolderScribe aprende de las
  correcciones del usuario y las ofrece como sugerencias futuras.
- **Búsqueda en lenguaje natural.** Consultar el índice local con frases como
  "facturas de enero".
- **Imágenes y capturas.** Clasificación por contenido visual.
- **Windows.** Soporte multiplataforma tras estabilizar el flujo principal.
- **Grafo de conocimiento.** Relaciones entre archivos, proyectos, personas y
  fechas.

## 7. Niveles de privacidad

| Nivel | Qué se procesa en local | Qué sale del equipo |
|-------|--------------------------|----------------------|
| Excluir | Nada. El archivo se omite. | Nada. |
| Solo metadatos | Fecha, tamaño, tipo MIME, nombre. | Nada. |
| Local | Metadatos + texto extraído + OCR. | Nada. |
| Completo | Todo el análisis. | El usuario puede optar por compartir patrones anónimos para mejorar el modelo. |

El usuario configura el nivel por archivo o por tipo. El valor predeterminado
es **local**.

## 8. Visión completa vs. alcance del MVP

Este documento describe la visión completa de FolderScribe. El MVP inicial es
significativamente más acotado y se define en `MVP.md`. Ninguna capacidad
futura incluida aquí forma parte del primer entregable a menos que esté
explícitamente recogida en ese documento.
