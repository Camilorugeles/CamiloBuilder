from builders.templated_component_builder import TemplatedComponentBuilder


class ServiceBuilder(TemplatedComponentBuilder):
    component_folder = "services"
    component_label = "Servicio"
    component_type = "service"
