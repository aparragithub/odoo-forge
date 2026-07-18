# El control plane llega con el segundo actor, no con el primero

Cerebro apunta a ser una autoridad central con estado (control plane) que gestione clientes e instancias. Decidimos **no** construir ese servidor en la primera bala trazadora. El journey del **Dev** —auto-servicio de instancias locales por nombre— no necesita estado compartido, porque cada dev trabaja aislado; se resuelve con lógica local dentro de la CLI, reusando el catálogo de proyectos y el backend Docker que ya existen. El control plane con estado persistente se justifica recién con el **Funcional**, cuyo journey ("¿a qué instancia de prueba entro?") sí exige un lugar central que sepa qué instancias existen y quién accede.

## Alternativas consideradas

- **Cerebro-servicio desde el día uno** (control plane corriendo, API, auth, store de estado). Rechazado: paga el costo de infra antes de validar la tesis de auto-servicio, y el Dev no lo necesita.
- **Deploy remoto como primera bala** (backend EC2/VPS nuevo). Rechazado: exige un adapter de backend nuevo y manejo de estado/credenciales remotas. La arquitectura hexagonal existe para hacer "local → remoto" barato *después*, una vez probado el átomo de auto-servicio.

## Consecuencias

- La primera bala reusa el flujo `forge run` y le da a `project_catalog` su **primer consumidor real**, tensando esa abstracción con uso en lugar de dejarla adivinada.
- Cuando llegue el Funcional, la resolución lógica se promueve a un servicio con aprendizaje real ya en la mano; los `ports` existentes son la costura por donde entra el control plane sin romper el core.
