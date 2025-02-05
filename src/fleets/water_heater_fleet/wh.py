# -*- coding: utf-8 -*-
"""
Created on Tue Oct 24 08:38:56 2017
super simple water heater model
@author: Chuck Booten (NREL), Jeff Maguire (NREL), Xin Jin (NREL)
"""

from fleets.water_heater_fleet.WH_Response import WHResponse


class WaterHeater():
    def __init__(self, Tamb=50, RHamb=45, Tmains=50, hot_draw=0, control_signal='none', Capacity=50, Type='ER',
                 Location='Conditioned', service_calls_accepted=0, max_service_calls=100, time_step=60,
                 forecast_draw=0):
        # Declare constants
        self.Tdeadband = 10  # delta F
        self.E_heat = 4.5  # kW
        self.UA = 10.  # W/K
        self.Tmin = 105.  # deg F
        self.Tmax = 160.  # deg F
        self.Capacity = Capacity  # gallons
        self.max_service_calls = int(max_service_calls)

    def execute(self, Ttank, Ttank_b, Tset, Tamb, RHamb, Tmains, hot_draw, control_signal, Type, timestep,
                forecast_draw, element_on_last):
        (response) = self.WH(Ttank, Ttank_b, Tset, Tamb, Tmains, hot_draw, control_signal, Type, timestep,
                             forecast_draw, element_on_last)

        return response  # Ttank, Tset, SoC, AvailableCapacityAdd, AvailableCapacityShed, service_calls_accepted, Eservice, is_available_add, is_available_shed, ElementOn, Eused, PusedMax

    def WH(self, Tlast, Tlast_b, Tset, Tamb_ts, Tmains_ts, hot_draw_ts, control_signal_ts, Type, timestep,
           forecast_draw, element_on_last):
        #############################################################################

        response = ()  # initialize
        #        Baseline operation
        P_request = control_signal_ts
        Eloss_ts_b = self.UA * (Tlast_b - float(Tamb_ts[0]))
        dT_from_hot_draw_b = (hot_draw_ts[0]) / self.Capacity * (
                    Tlast_b - float(Tmains_ts[0]))  # hot_draw is in gal for the timestep
        dT_loss_b = Eloss_ts_b * (timestep) / (
                    3.79 * self.Capacity * 4810)  # 3.79 kg/gal of water, 4810 is J/kgK heat capacity of water, timestep units are minutes
        Edel_ts_b = hot_draw_ts[0] * 4180 * 3.79 * (Tlast_b - float(Tmains_ts[0]))
        Element_on_ts = 0
        cycles_b = 0
        if Tlast_b < Tset - self.Tdeadband:
            Pused_baseline_ts = self.E_heat * 1000  # W used
            Element_on_ts = 1
            dT_power_input_b = (Pused_baseline_ts * timestep) / (3.79 * self.Capacity * 4810)
            Ttank_ts_b = Tlast_b + dT_power_input_b - dT_loss_b - dT_from_hot_draw_b
            cycles_b = 1
            if Ttank_ts_b > Tset:
                Pused_baseline_ts = (Tset + dT_loss_b + dT_from_hot_draw_b - Tlast_b) * (
                            3.79 * self.Capacity * 4810) / timestep
                Ttank_ts_b = Tset
        elif element_on_last == 1 and Tlast_b < Tset:  # and P_request == 0
            Pused_baseline_ts = self.E_heat * 1000  # W used
            Element_on_ts = 1
            dT_power_input_b = (Pused_baseline_ts * timestep) / (3.79 * self.Capacity * 4810)
            Ttank_ts_b = Tlast_b + dT_power_input_b - dT_loss_b - dT_from_hot_draw_b
            if Ttank_ts_b > Tset:
                Pused_baseline_ts = (Tset + dT_loss_b + dT_from_hot_draw_b - Tlast_b) * (
                            3.79 * self.Capacity * 4810) / timestep
                Ttank_ts_b = Tset
        else:
            Pused_baseline_ts = 0
            Element_on_ts = 0
            dT_power_input_b = 0
            Ttank_ts_b = Tlast_b + dT_power_input_b - dT_loss_b - dT_from_hot_draw_b

        SOC_b = (Ttank_ts_b - self.Tmin) / (self.Tmax - self.Tmin)
        Pbase = Pused_baseline_ts

        ###########################################################################
        # modify operation based on control signal
        max_service_calls = 100000000000
        service_calls_accepted_ts = 0

        Eloss_ts = self.UA * (Tlast - float(Tamb_ts[0]))
        dT_from_hot_draw = (hot_draw_ts[0]) / self.Capacity * (
                    Tlast - float(Tmains_ts[0]))  # hot_draw is in gal for the timestep
        dT_loss = Eloss_ts * (timestep) / (
                    3.79 * self.Capacity * 4810)  # 3.79 kg/gal of water, 4810 is J/kgK heat capacity of water, timestep units are minutes
        Edel_ts = hot_draw_ts[0] * 4180 * 3.79 * (Tlast - float(Tmains_ts[0]))
        # For the WHs providing service, start by performing normal operation
        if Tlast < Tset - self.Tdeadband:
            Pused_ts = self.E_heat * 1000  # W used
            Element_on_ts = 1
            dT_power_input = (Pused_ts * timestep) / (3.79 * self.Capacity * 4810)
            Ttank_ts = Tlast + dT_power_input - dT_loss - dT_from_hot_draw
            cycles = 1
            if Ttank_ts > Tset:
                Pused_ts = (Tset + dT_loss + dT_from_hot_draw - Tlast) * (3.79 * self.Capacity * 4810) / timestep
                Ttank_ts = Tset
        elif element_on_last == 1 and Tlast < Tset:  # and P_request == 0
            Pused_ts = self.E_heat * 1000  # W used
            Element_on_ts = 1
            dT_power_input = (Pused_ts * timestep) / (3.79 * self.Capacity * 4810)
            Ttank_ts = Tlast + dT_power_input - dT_loss - dT_from_hot_draw
            if Ttank_ts > Tset:
                Pused_ts = (Tset + dT_loss + dT_from_hot_draw - Tlast) * (3.79 * self.Capacity * 4810) / timestep
                Ttank_ts = Tset
        else:
            Pused_ts = 0
            Element_on_ts = 0
            dT_power_input = 0
            Ttank_ts = Tlast + dT_power_input - dT_loss - dT_from_hot_draw

        # If there's a service request, turn the WH on or off
        if P_request > 0 and Tlast > self.Tmin and max_service_calls > service_calls_accepted_ts and Element_on_ts == 1:  # Element_on_ts = 1 requirement eliminates free rider situation
            Pused_ts = 0  # make sure it stays off
            Element_on_ts = 0
            service_calls_accepted_ts += 1
        elif P_request > 0 and Tlast < self.Tmin:
            # don't change anything
            Pused_ts = 0
        elif P_request < 0 and Tlast > self.Tmax:
            if P_request < Pused_ts:
                Pused_ts = P_request
            else:
                Pused_ts = 0  # make sure it stays off
            Element_on_ts = 0
        elif P_request < 0 and Tlast < self.Tmax and max_service_calls > service_calls_accepted_ts and Element_on_ts == 0:  # Element_on_ts = 0 requirement eliminates free rider situation
            # make sure it stays on
            Pservice_max_ts = self.E_heat * 1000  # W used
            if Pservice_max_ts > P_request:
                Pused_ts = P_request
            else:
                Pused_ts = Pservice_max_ts
            Element_on_ts = 1
            service_calls_accepted_ts += 1
            cycles = 1
        # Otherwise there's no change

        # calculate energy provided as a service, >0 is load add, <0 load shed
        # if the magnitude of the service that could be provided is greater than what is requested, just use what is requested and adjust the element on time
        #        print('Available',abs(Eused_ts-Eused_baseline_ts), 'requested',control_signal_ts)

        if P_request != 0:
            Eservice_ts = Pused_ts - Pused_baseline_ts
        else:
            Eservice_ts = 0

        '''
        if abs(Pused_ts-Pused_baseline_ts) > abs(control_signal_ts): 
            Eservice_ts = control_signal_ts
            Pused_ts = control_signal_ts + Pused_baseline_ts
            Element_on_ts = control_signal_ts/(Pused_ts-Pused_baseline_ts)
        else: # assumes WH can't meet the entire request so it just does as much as it can
            Eservice_ts = Pused_ts-Pused_baseline_ts

        if P_request != 0:
            Eservice_ts = P_request
            Pused_ts = P_request + Pused_baseline_ts
            Element_on_ts = P_request/(Pused_ts-Pused_baseline_ts)
        else:
            Eservice_ts = 0
        '''
        # could change this at some point based on signals
        Tset_ts = Tset

        dT_power_input = (Pused_ts * timestep) / (3.79 * self.Capacity * 4810)
        Ttank_ts = Tlast + dT_power_input - dT_loss - dT_from_hot_draw

        cycles = 0
        if Pused_ts > 0 and Pused_baseline_ts == 0:
            cycles = 1

        #        Calculate more parameters to be passed up
        SOC = (Ttank_ts - self.Tmin) / (self.Tmax - self.Tmin)
        Estored = (Ttank_ts - self.Tmin) * self.Capacity * 62.4 * (1 / 7.48) / 3412.14

        ######################################################################################
        # simple method to forecast availability for providing a service during next timestep
        #        isAvailable_ts = 1 if max_service_calls > service_calls_accepted_ts  else 0
        # more advanced method for estimating availaibility based on the aggregator providing a fleet average water draw for the next timestep.
        dT_from_forecast_draw = -(forecast_draw) / self.Capacity * (Ttank_ts - Tmains_ts)
        Ttank_forecast = Ttank_ts + dT_from_forecast_draw

        isAvailable_add_ts = 1 if max_service_calls > service_calls_accepted_ts and Ttank_forecast < self.Tmax and (
                    Ttank_forecast > Tset - self.Tdeadband and Element_on_ts == 0 or Ttank_forecast > Tset + self.Tdeadband) > 0 else 0  # haven't exceeded max number of calls, plus it isn't expected that the element would already be on due to the forecast temperature being below Tset- Tdeadband but are still expected to be below Tmax
        isAvailable_shed_ts = 1 if max_service_calls > service_calls_accepted_ts and Ttank_forecast > self.Tmin and (
                    Ttank_forecast < Tset + self.Tdeadband and Element_on_ts > 0 or Ttank_forecast < Tset - self.Tdeadband) > 0 else 0  # haven't exceeded max number of calls, plus it is expected that the element would already be on due to the forecast temperature being below Tset + Tdeadband but are still expected to be above Tmin
        ######################################################################################

        # estimate on what the maximum power usage could be based on initial temps, expected dT from water draw, dT loss and COP
        if Type == "HP":
            COP = 2.5  # this shouldn't be constant, just a placeholder for now
        else:  # assumes electric resistance
            COP = 1

        Texpected = Tlast - dT_from_hot_draw - dT_loss
        PusedMax_ts = (self.Tmax - Texpected) * (
                    3.79 * self.Capacity * 4810) / COP / timestep  # units: [W]  3.79 kg/gal of water, 4810 is J/kgK heat capacity of water
        PusedMin_ts = 0
        Available_Capacity_Add = float(
            (1 - SOC) * self.Capacity * 3.79 * 4180 * (self.Tmax - self.Tmin) * isAvailable_add_ts / (
                timestep))  # /timestep converts from Joules to Watts, 3.79 = kg/gal, 4180 heat cap of water J/kgK
        Available_Capacity_Shed = float(
            SOC * self.Capacity * 3.79 * 4180 * (self.Tmax - self.Tmin) * isAvailable_shed_ts / (
                timestep))  # /timestep*60 converts from Joules to Watts,

        response = WHResponse()

        response.Ttank = Ttank_ts
        response.Ttank_b = Ttank_ts_b
        response.Tset = Tset_ts
        response.Eused = Pused_ts
        response.Pbase = Pbase
        response.PusedMax = PusedMax_ts
        response.PusedMin = PusedMin_ts
        response.Eloss = Eloss_ts
        response.Edel = Edel_ts
        response.ElementOn = Element_on_ts
        response.Eservice = float(Eservice_ts)
        response.Estored = Estored
        response.SOC = SOC
        response.SOC_b = SOC_b
        response.AvailableCapacityAdd = Available_Capacity_Add
        response.AvailableCapacityShed = Available_Capacity_Shed
        response.ServiceCallsAccepted = service_calls_accepted_ts
        response.IsAvailableAdd = isAvailable_add_ts
        response.IsAvailableShed = isAvailable_shed_ts
        response.cycles = cycles
        response.cycles_b = cycles_b

        return response


if __name__ == '__main__':
    main()