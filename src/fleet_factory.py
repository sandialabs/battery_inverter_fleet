from datetime import datetime
from grid_info import GridInfo


def create_fleet(name, grid_type=1, **kwargs):
    if grid_type == 2:
        from grid_info_artificial_inertia import GridInfo  #Use for artificial Inertia case
        grid = GridInfo('Grid_Info_data_artificial_inertia.csv')
    else:
        from grid_info import GridInfo
        grid = GridInfo('Grid_Info_DATA_2.csv')

    if name == 'BatteryInverter':
        from fleets.battery_inverter_fleet.battery_inverter_fleet import BatteryInverterFleet
        battery_inverter_fleet = BatteryInverterFleet(GridInfo=grid, model_type='ERM')
        battery_inverter_fleet.is_autonomous = False
        if 'autonomous' in kwargs and kwargs['autonomous']:
            battery_inverter_fleet.is_autonomous = True
        battery_inverter_fleet.VV11_Enabled = False
        battery_inverter_fleet.FW21_Enabled = False

        return battery_inverter_fleet

    elif name == 'ElectricVehicle':
        from fleets.electric_vehicles_fleet.electric_vehicles_fleet import ElectricVehiclesFleet

        # Time stamp to start the simulation
        # Please, ensure that the timestamp is the same timestamp passed at the
        # beginning of the service request
        ts = kwargs['start_time'] # Read it from kwargs dictionary

        ev_fleet = ElectricVehiclesFleet(grid, ts)
        ev_fleet.is_autonomous = False
        ev_fleet.is_P_priority = True
        ev_fleet.service_weight = kwargs['service_weight']
        if 'autonomous' in kwargs and kwargs['autonomous']:
           ev_fleet.is_autonomous = True
        ev_fleet.VV11_Enabled = False
        ev_fleet.FW21_Enabled = True

        return ev_fleet

    elif name == 'PV':
        from fleets.PV.PV_Inverter_Fleet import PVInverterFleet
        fleet = PVInverterFleet(GridInfo=grid)
        fleet.service_weight = kwargs['service_weight']
        if 'autonomous' in kwargs and kwargs['autonomous']:
           fleet.is_autonomous = True
        else:
           fleet.is_autonomous = False
        fleet.VV11_Enabled = False
        fleet.FW21_Enabled = True
        return fleet

    elif name == 'WaterHeater':
        from fleets.water_heater_fleet.wh_fleet import WaterHeaterFleet
        ts = kwargs['start_time']
        s_step = kwargs['sim_step']
        fleet = WaterHeaterFleet(grid, ts, s_step)
        if 'autonomous' in kwargs and kwargs['autonomous']:
           fleet.is_autonomous = True
        else:
           fleet.is_autonomous = False
        fleet.VV11_Enabled = False
        fleet.FW21_Enabled = True
        return fleet

    elif name == 'Electrolyzer':
        from fleets.electrolyzer_fleet.ey_fleet import ElectrolyzerFleet
        fleet = ElectrolyzerFleet(grid, "config.ini", "Electrolyzer")
        if 'autonomous' in kwargs and kwargs['autonomous']:
           fleet.is_autonomous = True
           fleet.is_P_priority = False
        else:
           fleet.is_autonomous = False
        fleet.FW21_Enabled = True
        return fleet

    elif name == 'FuelCell':
        from fleets.fuel_cell_fleet.fuelcell_fleet import FuelCellFleet
        fleet = FuelCellFleet(grid, "config.ini", "FuelCell")
        if 'autonomous' in kwargs and kwargs['autonomous']:
           fleet.is_autonomous = True
           fleet.is_P_priority = False
        else:
           fleet.is_autonomous = False
        fleet.FW21_Enabled = True
        return fleet


    elif name == 'HVAC':
        from fleets.HVAC_fleet.HVAC_fleet import HVACFleet

        # Time stamp to start the simulation
        # Please, ensure that the timestamp is the same timestamp passed at the
        # beginning of the service request
        ts = kwargs['start_time'] # Read it from kwargs dictionary
        s_step = kwargs['sim_step']  # Read it from kwargs dictionary

        hvac_fleet = HVACFleet(grid, ts, s_step)
        hvac_fleet.is_autonomous = False
        hvac_fleet.is_P_priority = True
        hvac_fleet.service_weight = kwargs['service_weight']
        if 'autonomous' in kwargs and kwargs['autonomous']:
           hvac_fleet.is_autonomous = True
        hvac_fleet.VV11_Enabled = False
        hvac_fleet.FW21_Enabled = True

        return hvac_fleet

    elif name == 'Refridge':
        from fleets.Refridge_fleet.fridge_Fleet import RFFleet

        # Time stamp to start the simulation
        # Please, ensure that the timestamp is the same timestamp passed at the
        # beginning of the service request
        ts = kwargs['start_time'] # Read it from kwargs dictionary
        s_step = kwargs['sim_step']  # Read it from kwargs dictionary

        fridge_fleet = RFFleet(grid, ts, s_step)
        fridge_fleet.is_autonomous = False
        fridge_fleet.is_P_priority = True
        fridge_fleet.service_weight = kwargs['service_weight']
        if 'autonomous' in kwargs and kwargs['autonomous']:
           fridge_fleet.is_autonomous = True
        fridge_fleet.VV11_Enabled = False
        fridge_fleet.FW21_Enabled = True

        return fridge_fleet


    raise "There is no fleet with name: " + name
