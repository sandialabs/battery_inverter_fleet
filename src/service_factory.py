def create_service(name, **kwargs):
    if name == 'Regulation':
        from services.reg_service.reg_service import RegService

        return RegService()

    elif name == 'ArtificialInertia':
        from services.artificial_inertia_service.artificial_inertia_service import ArtificialInertiaService
        return ArtificialInertiaService()

    elif name == 'Reserve':
        from services.reserve_service.reserve_service import ReserveService

        return ReserveService()

    raise "There is no service with name: " + name

