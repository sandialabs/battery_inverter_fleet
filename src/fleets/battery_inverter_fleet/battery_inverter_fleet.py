# -*- coding: utf-8 -*- {{{
#
# Your license here
# }}}
import sys
from os.path import dirname, abspath, join
sys.path.insert(0,dirname(dirname(dirname(abspath(__file__)))))

import configparser
from datetime import datetime, timedelta
import numpy  
import copy 
import math

from fleet_interface import FleetInterface
from fleet_request import FleetRequest
from fleet_response import FleetResponse


class BatteryInverterFleet(FleetInterface):
    """
    This class implements FleetInterface so that it can communicate with a fleet
    """

    def __init__(self, model_type="ERM", **kwargs):
        """
        Constructor
        """
        self.model_type = model_type
        
        # Get cur directory
        base_path = dirname(abspath(__file__))

        # Read config file
        self.config = configparser.ConfigParser()
        self.config.read(join(base_path, 'config.ini'))

        # Load config info with default values if there is no such config parameter in the config file
        self.name = self.config.get(self.model_type, 'Name', fallback='Battery Inverter Fleet')
        
        # Load different parameters for the energy reservoir model (ERM), or the charge reservoir model (CRM)
        if self.model_type == "ERM":
            self.max_power_charge = float(self.config.get(self.model_type, 'MaxPowerCharge', fallback=10))
            self.max_power_discharge = float(self.config.get(self.model_type, 'MaxPowerDischarge', fallback=10))
            self.max_apparent_power = float(self.config.get(self.model_type, 'MaxApparentPower', fallback=-10))
            self.min_pf = float(self.config.get(self.model_type, 'MinPF', fallback=0.8))
            self.max_soc = float(self.config.get(self.model_type, 'MaxSoC', fallback=100))
            self.min_soc = float(self.config.get(self.model_type, 'MinSoC', fallback=0))
            self.energy_capacity = float(self.config.get(self.model_type, 'EnergyCapacity', fallback=10))
            self.energy_efficiency = float(self.config.get(self.model_type, 'EnergyEfficiency', fallback=1))
            self.self_discharge_power = float(self.config.get(self.model_type, 'SelfDischargePower', fallback=0))
            self.max_ramp_up = float(self.config.get(self.model_type, 'MaxRampUp', fallback=10))
            self.max_ramp_down = float(self.config.get(self.model_type, 'MaxRampDown', fallback=10))
            self.num_of_devices = int(self.config.get(self.model_type, 'NumberOfDevices', fallback=10))
            # system states
            self.t = float(self.config.get(self.model_type, 't', fallback=10))
            self.soc = float(self.config.get(self.model_type, 'soc', fallback=10))
            self.cap = float(self.config.get(self.model_type, 'cap', fallback=10))
            self.maxp = float(self.config.get(self.model_type, 'maxp', fallback=10))
            self.minp = float(self.config.get(self.model_type, 'minp', fallback=10))
            self.maxp_fs = float(self.config.get(self.model_type, 'maxp_fs', fallback=10))
            self.rru = float(self.config.get(self.model_type, 'rru', fallback=10))
            self.rrd = float(self.config.get(self.model_type, 'rrd', fallback=10))
            self.ceff = float(self.config.get(self.model_type, 'ceff', fallback=10))
            self.deff = float(self.config.get(self.model_type, 'deff', fallback=10))
            self.P_req =float( self.config.get(self.model_type, 'P_req', fallback=10))
            self.Q_req = float(self.config.get(self.model_type, 'Q_req', fallback=10))
            self.P_injected = float(self.config.get(self.model_type, 'P_injected', fallback=0))
            self.Q_injected = float(self.config.get(self.model_type, 'Q_injected', fallback=0))
            self.P_service = float(self.config.get(self.model_type, 'P_service', fallback=0))
            self.Q_service = float(self.config.get(self.model_type, 'Q_service', fallback=0))
            self.es = float(self.config.get(self.model_type, 'es', fallback=10))
        
            self.fleet_model_type = self.config.get(self.model_type, 'FleetModelType', fallback='Uniform')
            if self.fleet_model_type == 'Uniform':
                self.soc = numpy.repeat(self.soc,self.num_of_devices)
            if self.fleet_model_type == 'Standard Normal SoC Distribution':
                self.soc_std = float(self.config.get(self.model_type, 'SOC_STD', fallback=0)) # Standard deveation of SoC spread
                self.soc = numpy.repeat(self.soc,self.num_of_devices) + self.soc_std * numpy.random.randn(self.num_of_devices) 
                for i in range(self.num_of_devices):
                    if self.soc[i] > self.max_soc:
                        self.soc[i] = self.max_soc
                    if self.soc[i] < self.min_soc:
                        self.soc[i] = self.min_soc
            self.P_injected = numpy.repeat(self.P_injected,self.num_of_devices)
            self.Q_injected = numpy.repeat(self.Q_injected,self.num_of_devices)
        elif self.model_type == "CRM":
            self.energy_capacity = float(self.config.get(self.model_type, 'EnergyCapacity', fallback=10))
            # inverter parameters
            self.inv_name = self.config.get(self.model_type, 'InvName', fallback='Name')
            self.inv_type = self.config.get(self.model_type, 'InvType', fallback='Not Defined')
            self.coeff_0 = float(self.config.get(self.model_type, 'Coeff0', fallback=0))
            self.coeff_1 = float(self.config.get(self.model_type, 'Coeff1', fallback=1))
            self.coeff_2 = float(self.config.get(self.model_type, 'Coeff2', fallback=0))
            self.max_power_charge = float(self.config.get(self.model_type, 'MaxPowerCharge', fallback=10))
            self.max_power_discharge = float(self.config.get(self.model_type, 'MaxPowerDischarge', fallback=-10))
            self.max_apparent_power = float(self.config.get(self.model_type, 'MaxApparentPower', fallback=-10))
            self.min_pf = float(self.config.get(self.model_type, 'MinPF', fallback=0.8))
            self.max_ramp_up = float(self.config.get(self.model_type, 'MaxRampUp', fallback=10))
            self.max_ramp_down = float(self.config.get(self.model_type, 'MaxRampDown', fallback=10))
            # battery parameters
            self.bat_name = self.config.get(self.model_type, 'BatName', fallback='Name')
            self.bat_type = self.config.get(self.model_type, 'BatType', fallback='Not Defined')
            self.n_cells = float(self.config.get(self.model_type, 'NCells', fallback=10))
            self.voc_model_type = self.config.get(self.model_type, 'VOCModelType', fallback='Linear')
            if self.voc_model_type == 'Linear': # note all model values assume SoC ranges from 0% to 100%
                self.voc_model_m = float(self.config.get(self.model_type, 'VOC_Model_M', fallback=0.005))
                self.voc_model_b = float(self.config.get(self.model_type, 'VOC_Model_b', fallback=1.8))
            if self.voc_model_type == 'Quadratic':
                self.voc_model_a = float(self.config.get(self.model_type, 'VOC_Model_A', fallback=0.005))
                self.voc_model_b = float(self.config.get(self.model_type, 'VOC_Model_B', fallback=1.8))
                self.voc_model_c = float(self.config.get(self.model_type, 'VOC_Model_C', fallback=1.8))
            if self.voc_model_type == 'Cubic':
                self.voc_model_a = float(self.config.get(self.model_type, 'VOC_Model_A', fallback=0.005))
                self.voc_model_b = float(self.config.get(self.model_type, 'VOC_Model_B', fallback=1.8))
                self.voc_model_c = float(self.config.get(self.model_type, 'VOC_Model_C', fallback=1.8))
                self.voc_model_d = float(self.config.get(self.model_type, 'VOC_Model_D', fallback=1.8))
            if self.voc_model_type == 'CubicSpline':
                SoC_list = self.config.get(self.model_type, 'VOC_Model_SOC_LIST', fallback=0.005)
                list_hold = SoC_list.split(',')
                self.voc_model_SoC_list = [float(e) for e in list_hold]
                a_list = self.config.get(self.model_type, 'VOC_Model_A', fallback=0.005)
                b_list = self.config.get(self.model_type, 'VOC_Model_B', fallback=0.005)
                c_list = self.config.get(self.model_type, 'VOC_Model_C', fallback=0.005)
                d_list = self.config.get(self.model_type, 'VOC_Model_D', fallback=0.005)
                list_hold = a_list.split(',')
                self.voc_model_a = [float(e) for e in list_hold]
                list_hold = b_list.split(',')
                self.voc_model_b = [float(e) for e in list_hold]
                list_hold = c_list.split(',')
                self.voc_model_c = [float(e) for e in list_hold]
                list_hold = d_list.split(',')
                self.voc_model_d = [float(e) for e in list_hold]
            self.max_current_charge = float(self.config.get(self.model_type, 'MaxCurrentCharge', fallback=10))
            self.max_current_discharge = float(self.config.get(self.model_type, 'MaxCurrentDischarge', fallback=-10))
            self.max_voltage = float(self.config.get(self.model_type, 'MaxVoltage', fallback=58))
            self.min_voltage= float(self.config.get(self.model_type, 'MinVoltage', fallback=48))
            self.max_soc = float(self.config.get(self.model_type, 'MaxSoC', fallback=100))
            self.min_soc = float(self.config.get(self.model_type, 'MinSoC', fallback=0))
            self.charge_capacity = float(self.config.get(self.model_type, 'ChargeCapacity', fallback=10))
            self.coulombic_efficiency = float(self.config.get(self.model_type, 'CoulombicEfficiency', fallback=1))
            self.self_discharge_current = float(self.config.get(self.model_type, 'SelfDischargeCurrent', fallback=0))
            self.r0 = float(self.config.get(self.model_type, 'R0', fallback=0))
            self.r1 = float(self.config.get(self.model_type, 'R1', fallback=0))
            self.r2 = float(self.config.get(self.model_type, 'R2', fallback=0))
            self.c1 = float(self.config.get(self.model_type, 'C1', fallback=0))
            self.c2 = float(self.config.get(self.model_type, 'C2', fallback=0))
            # fleet parameters
            self.num_of_devices = int(self.config.get(self.model_type, 'NumberOfDevices', fallback=10))
            # battery system states
            self.t = float(self.config.get(self.model_type, 't', fallback=0))
            self.soc = float(self.config.get(self.model_type, 'soc', fallback=50))
            self.v1 = float(self.config.get(self.model_type, 'v1', fallback=0))
            self.v2 = float(self.config.get(self.model_type, 'v2', fallback=0))
            self.voc = float(self.config.get(self.model_type, 'voc', fallback=53))
            self.vbat = float(self.config.get(self.model_type, 'vbat', fallback=53))
            self.ibat = float(self.config.get(self.model_type, 'ibat', fallback=0))
            self.pdc = float(self.config.get(self.model_type, 'pdc', fallback=0))
            self.cap = float(self.config.get(self.model_type, 'cap', fallback=10.6))
            self.maxp = float(self.config.get(self.model_type, 'maxp', fallback=10))
            self.minp = float(self.config.get(self.model_type, 'minp', fallback=-10))
            self.maxp_fs = float(self.config.get(self.model_type, 'maxp_fs', fallback=0))
            self.rru = float(self.config.get(self.model_type, 'rru', fallback=10))
            self.rrd = float(self.config.get(self.model_type, 'rrd', fallback=-10))
            self.ceff = float(self.config.get(self.model_type, 'ceff', fallback=1))
            self.deff = float(self.config.get(self.model_type, 'deff', fallback=1))
            self.P_req = float(self.config.get(self.model_type, 'P_req', fallback=0))
            self.Q_req = float(self.config.get(self.model_type, 'Q_req', fallback=0))
            self.P_injected = float(self.config.get(self.model_type, 'P_injected', fallback=0))
            self.Q_injected = float(self.config.get(self.model_type, 'Q_injected', fallback=0))
            self.P_service = float(self.config.get(self.model_type, 'P_service', fallback=0))
            self.Q_service = float(self.config.get(self.model_type, 'Q_service', fallback=0))
            self.es = float(self.config.get(self.model_type, 'es', fallback=5.3))
            
            self.fleet_model_type = self.config.get(self.model_type, 'FleetModelType', fallback='Uniform')
            if self.fleet_model_type == 'Uniform':
                self.soc = numpy.repeat(self.soc,self.num_of_devices)
            if self.fleet_model_type == 'Standard Normal SoC Distribution':
                self.soc_std = float(self.config.get(self.model_type, 'SOC_STD', fallback=0)) # Standard deveation of SoC spread
                self.soc = numpy.repeat(self.soc,self.num_of_devices) + self.soc_std * numpy.random.randn(self.num_of_devices) 
                for i in range(self.num_of_devices):
                    if self.soc[i] > self.max_soc:
                        self.soc[i] = self.max_soc
                    if self.soc[i] < self.min_soc:
                        self.soc[i] = self.min_soc
            self.v1 = numpy.repeat(self.v1,self.num_of_devices)
            self.v2 = numpy.repeat(self.v2,self.num_of_devices)
            self.voc = numpy.repeat(self.voc,self.num_of_devices)
            self.vbat = numpy.repeat(self.vbat,self.num_of_devices)
            self.ibat = numpy.repeat(self.ibat,self.num_of_devices)
            self.pdc = numpy.repeat(self.pdc,self.num_of_devices)
            self.maxp = numpy.repeat(self.maxp,self.num_of_devices)
            self.minp = numpy.repeat(self.minp,self.num_of_devices)
            self.P_injected = numpy.repeat(self.P_injected,self.num_of_devices)
            self.Q_injected = numpy.repeat(self.Q_injected,self.num_of_devices)
        else: 
            print('Error: ModelType not selected as either energy reservoir model (self), or charge reservoir model (self)')
            print('Battery-Inverter model config unable to continue. In config.ini, set ModelType to self or self')

        

    def process_request(self, FleetRequest):
        """
        The expectation that configuration will have at least the following
        items

        :param fleet_request: an instance of FleetRequest

        :return res: an instance of FleetResponse
        """
        dt = FleetRequest.sim_step
        p_req = FleetRequest.P_req
        q_req = FleetRequest.Q_req

        # call run function with proper inputs
        FleetResponse = self.run(p_req,q_req, dt)

        return FleetResponse

    def run(self, P_req=[0], Q_req=[0], del_t=timedelta(hours=1)):
        np = numpy.ones(self.num_of_devices,int)
        nq = numpy.ones(self.num_of_devices,int)
        p_req = P_req/self.num_of_devices
        q_req = Q_req/self.num_of_devices
        p_tot = 0
        q_tot = 0
        dt = del_t.total_seconds() / 3600.0 
        self.t = self.t + dt
        
        response = FleetResponse()

        last_P = numpy.zeros(self.num_of_devices,int)
        last_Q = numpy.zeros(self.num_of_devices,int)
        soc_update = copy.copy(self.soc)
        if self.model_type == 'CRM':
            pdc_update = self.pdc
            ibat_update = self.ibat
            v1_update = self.v1
            v2_update = self.v2
            vbat_update = self.vbat
        

        for i in range(self.num_of_devices):
            last_P[i] = self.P_injected[i]
            last_Q[i] = self.Q_injected[i]
            self.P_injected[i] = 0
            self.Q_injected[i] = 0
        TOL = 0.000001 # tollerance
        while ((p_tot < P_req-TOL or p_tot > P_req+TOL) or  (q_tot < Q_req-TOL or q_tot > Q_req+TOL)) and sum(np)!=0 and sum(nq)!=0: #continue looping through devices until the power needs are met or all devices are at their limits
            # distribute the requested power equally among the devices that are not at their limits
            p_req = (P_req - p_tot)/sum(np)
            q_req = (Q_req - q_tot)/sum(nq)
            for i in range(self.num_of_devices):
                if np[i] == 1 or nq[i] == 1:

                    #  Max ramp rate and apparent power limit checking
                    if np[i] == 1 :
                        p_ach = self.P_injected[i] + p_req
                        if (p_ach-last_P[i]) > self.max_ramp_up:
                            p_ach = self.max_ramp_up + last_P[i]
                            np[i] = 0
                        elif (p_ach-last_P[i]) < self.max_ramp_down:
                            p_ach = self.max_ramp_down + last_P[i]
                            np[i] = 0
                            
                        if p_ach < self.max_power_discharge:
                            p_ach  = self.max_power_discharge
                            np[i] = 0
                        if p_ach > self.max_power_charge:
                            p_ach = self.max_power_charge
                            np[i] = 0
                    else:
                        p_ach = self.P_injected[i] 

                    if nq[i] == 1:
                        q_ach = self.Q_injected[i] + q_req
                        if (q_ach-last_Q[i]) > self.max_ramp_up:
                            q_ach = self.max_ramp_up + last_Q[i]
                            nq[i] = 0
                        elif (q_ach-last_Q[i]) < self.max_ramp_down:
                            q_ach = self.max_ramp_down + last_Q[i]
                            nq[i] = 0
                    else:
                        q_ach = self.Q_injected[i] 
                    
                    S_req = float(numpy.sqrt(p_ach**2 + q_ach**2))
                    
                    # watt priority
                    if S_req > self.max_apparent_power:
                        q_ach = float(numpy.sqrt(numpy.abs(self.max_apparent_power**2 - p_ach**2)) * numpy.sign(q_ach))
                        S_req = self.max_apparent_power
                    # var priority
                    """ if S_req > self.max_apparent_power:
                        p_ach = float(numpy.sqrt(numpy.abs(self.max_apparent_power**2 - q_ach**2)) * numpy.sign(p_ach))
                        S_req = self.max_apparent_power """
                    # check power factor limit
                    if p_ach != 0.0: 
                        if float(numpy.abs(S_req/p_ach)) < self.min_pf:
                            q_ach =  float(numpy.sqrt(numpy.abs((p_ach/self.min_pf)**2 - p_ach**2)) * numpy.sign(q_ach))

                    
                    if np[i] == 1:
                        # run function for ERM model type
                        if self.model_type == 'ERM':
                            # Calculate SoC_update and Power Achieved
                            Ppos = min(self.max_power_charge, max(p_ach, 0))
                            Pneg = max(self.max_power_discharge, min(p_ach, 0))
                            soc_update[i] = self.soc[i] + float(100) * dt * (Pneg + (
                                Ppos * self.energy_efficiency) + self.self_discharge_power) / self.energy_capacity
                            if soc_update[i] > self.max_soc:
                                Ppos = (self.energy_capacity * (self.max_soc - self.soc[i]) / (
                                    float(100) * dt) - self.self_discharge_power) / self.energy_efficiency
                                soc_update[i] = self.max_soc
                                np[i] = 0
                            if soc_update[i] < self.min_soc:
                                Pneg = self.energy_capacity * (self.min_soc - self.soc[i]) / (
                                    float(100) * dt) - self.self_discharge_power
                                soc_update[i] = self.min_soc
                                np[i] = 0                                    

                            p_ach = (Ppos + Pneg)
                            q_ach =  q_ach
                            self.P_injected[i] = p_ach
                            self.Q_injected[i] = q_ach
                        # run function for CRM model type
                        elif self.model_type == 'CRM':
                            # convert AC power p_ach to DC power pdc
                            pdc_update[i] = self.coeff_2*(p_ach**2)+self.coeff_1*(p_ach)+self.coeff_0 

                            # convert DC power pdc to DC current
                            b = ((self.v1[i] + self.v2[i]+ self.voc[i])*self.n_cells) 
                            a = self.r0 * self.n_cells 
                            c = -pdc_update[i] * 1000
                            ibat_update[i] = (-b+numpy.sqrt(b**2 - 4*a*c))/(2*a)
                            
                            # calculate dynamic voltages
                            v1_update[i] = self.v1[i] + dt *( (1/(self.r1*self.c1))*self.v1[i] + (1/(self.c1))*ibat_update[i])
                            v2_update[i] = self.v2[i] + dt *( (1/(self.r2*self.c2))*self.v2[i] + (1/(self.c2))*ibat_update[i])
                            vbat_update[i] = (v1_update[i]  + v2_update[i] + self.voc[i] + ibat_update[i]*self.r0) *self.n_cells

                            # Calculate SoC and Power Achieved
                            Ipos = min(self.max_current_charge, max(ibat_update[i], 0))
                            Ineg = max(self.max_current_discharge, min(ibat_update[i], 0))
                            soc_update[i] = self.soc[i] + float(100) * dt * (Ineg + (
                                Ipos * self.coulombic_efficiency) + self.self_discharge_current) / self.charge_capacity
                            if soc_update[i] > self.max_soc:
                                Ipos = self.charge_capacity *((self.max_soc - self.soc[i] )/ (float(100) * dt) - self.self_discharge_current) / self.coulombic_efficiency
                                soc_update[i] = self.max_soc
                                np[i] = 0
                                pdc_update[i]  = Ipos *vbat_update[i] / 1000
                                if self.coeff_2 != 0:
                                    p_ach = (-self.coeff_1 +float(numpy.sqrt(self.coeff_1**2 - 4*self.coeff_2*(self.coeff_0-pdc_update[i]))))/(2*self.coeff_2)
                                else: 
                                    p_ach  = (pdc_update[i] - self.coeff_0)/self.coeff_1
                            if soc_update[i] < self.min_soc:
                                Ineg = self.charge_capacity * (self.min_soc - self.soc[i]) / (
                                    float(100) * dt) - self.self_discharge_current
                                soc_update[i] = self.min_soc
                                np[i] = 0                                    
                                pdc_update[i]  = Ineg *vbat_update[i] / 1000
                                if self.coeff_2 != 0:
                                    p_ach = (-self.coeff_1 +float(numpy.sqrt(self.coeff_1**2 - 4*self.coeff_2*(self.coeff_0-pdc_update[i]))))/(2*self.coeff_2)
                                else: 
                                    p_ach  = (pdc_update[i] - self.coeff_0)/self.coeff_1
                            
                            ibat_update[i] = Ipos + Ineg
                            v1_update[i] = self.v1[i] + dt *( (1/(self.r1*self.c1))*self.v1[i] + (1/(self.c1))*ibat_update[i])
                            v2_update[i] = self.v2[i] + dt *( (1/(self.r2*self.c2))*self.v2[i] + (1/(self.c2))*ibat_update[i])
                            vbat_update[i] = (v1_update[i]  + v2_update[i] + self.voc[i] + ibat_update[i]*self.r0) *self.n_cells
                            self.P_injected[i] = p_ach
                            self.Q_injected[i] = q_ach

            # at the end of looping through the devices, add up their power to determine if the request has been met
            p_tot = sum(self.P_injected)
            q_tot = sum(self.Q_injected)
        # update SoC
        self.soc = soc_update
        if self.model_type == 'CRM':
            self.v1 = v1_update
            self.v2 = v2_update
            self.voc_update()
            self.ibat = ibat_update
            self.vbat = (self.v1 + self.v2 + self.voc + self.ibat*self.r0) *self.n_cells
        # once the power request has been met, or all devices are at their limits, return the response variables
        response.P_injected = p_tot
        response.Q_injected = q_tot  
        response.soc = numpy.average(self.soc)
        response.E = numpy.average(self.soc) * self.energy_capacity / 100.0
        return response 
    
    def voc_update(self): 
        s = self.soc/100
        for i in range(self.num_of_devices):
            if self.voc_model_type== "Linear":
                self.voc[i] = self.voc_model_m*s[i] + self.voc_model_b
            elif self.voc_model_type == "Quadratic":
                self.voc[i] = self.voc_model_a*(s[i]**2) + self.voc_model_b*s[i] + self.voc_model_c
            elif self.voc_model_type == "Cubic":
                self.voc[i] = self.voc_model_a*(s[i]**3) + self.voc_model_b*(s[i]**2) + self.voc_model_c*s[i] + self.voc_model_d
            elif self.voc_model_type == "CubicSpline":
                j = 0
                for s_cnt in self.voc_model_SoC_list:
                    if s[i] > s_cnt:
                        j = j + 1
                self.voc = self.voc_model_a[j]*(s[i]**3) + self.voc_model_b[j]*(s[i]**2) + self.voc_model_c[j]*s[i] + self.voc_model_d[j]
            else:
                print('Error: open circuit voltage (voc) model type (voc_model_type) is not defined properly')
                print('in config_self.ini set VocModelType=Linear or =CubicSpline')
            pass

    def voc_query(self,SOC): 
        SOC = SOC/100
        if self.voc_model_type== "Linear":
            VOC = self.voc_model_m*SOC + self.voc_model_b
        elif self.voc_model_type == "Quadratic":
            VOC = self.voc_model_a*(SOC**2) + self.voc_model_b*SOC + self.voc_model_c
        elif self.voc_model_type == "Cubic":
            VOC = self.voc_model_a*(SOC**3) + self.voc_model_b*(SOC**2) + self.voc_model_c*SOC + self.voc_model_d
        elif self.voc_model_type == "CubicSpline":
            j = 0
            for s in self.voc_model_SoC_list:
                if SOC > s:
                    j = j + 1
            VOC = self.voc_model_a[j]*(SOC**3) + self.voc_model_b[j]*(SOC**2) + self.voc_model_c[j]*SOC + self.voc_model_d[j]
        else:
            print('Error: open circuit voltage (voc) model type (voc_model_type) is not defined properly')
            print('in config_self.ini set VocModelType=Linear or =CubicSpline')
        return VOC

    def cost(self, initSoC = 50,finSoC = 50,del_t=timedelta(hours=1)):
        import numpy
        # pre-define variables
        Cost = 0
        Able = 1
        Power = 0
        dt = del_t.total_seconds() / 3600.0 
        # impose SoC constraints
        if initSoC > self.max_soc:
            Able = 0
        if initSoC < self.min_soc:
            Able = 0
        if finSoC > self.max_soc:
            Able = 0
        if finSoC < self.min_soc:
            Able = 0

        if self.model_type == 'ERM':
            DSoC = finSoC - initSoC
            if DSoC >= 0:
                Power = ((self.energy_capacity * DSoC / (float(100)*dt)) - self.self_discharge_power)/self.energy_efficiency
            if DSoC < 0:
                Power = (self.energy_capacity * DSoC / (float(100)*dt)) - self.self_discharge_power
            # linear power cost function
        #     Cost = Power*0.01
            # quadratic power cost function
        #     Cost = Power*Power*0.01
            Ppos = max(Power,0)
            Pneg = min(Power,0)
            # inpose power constraints
            if Ppos > self.max_power_charge:
                Able = 0
                Power = 0
            if Pneg < self.max_power_discharge:
                Able = 0
                Power = 0
        if self.model_type == 'CRM':
            Current = 0
            DSoC = finSoC - initSoC
            # Calculate battery current
            if DSoC >= 0:
                Current = ((self.charge_capacity * DSoC / (float(100)*dt)) - self.self_discharge_current)/self.coulombic_efficiency
            if DSoC < 0:
                Current = ((self.charge_capacity * DSoC / (float(100)*dt)) - self.self_discharge_current)
            Voltage = (Current*self.r0+((self.voc_query(initSoC)+self.voc_query(finSoC))/2))
            PowerDC =  self.n_cells*Current*(Voltage)/1000
            if self.coeff_2 != 0:
                Power = (-self.coeff_1 +float(numpy.sqrt(self.coeff_1**2 - 4*self.coeff_2*(self.coeff_0-PowerDC))))/(2*self.coeff_2)
                if math.isnan(Power):
                    Power  = (PowerDC - self.coeff_0)/self.coeff_1
            else: 
                Power  = (PowerDC - self.coeff_0)/self.coeff_1

            Ipos = max(Current,0)
            Ineg = min(Current,0)
            # impose current limites
            if Ipos > self.max_current_charge:
                Able = 0
                Power = 0
                Current = 0
            if Ineg < self.max_current_discharge:
                Able = 0
                Power = 0
                Current = 0
            # impose voltage limites
            if Voltage > self.max_voltage:
                Voltage = self.max_voltage
                Able = 0
                Power = 0
                Current = 0
            if Voltage < self.min_voltage:
                Voltage = self.min_voltage
                Able = 0
                Power = 0
                Current = 0 
                
            Ppos = max(Power,0)
            Pneg = min(Power,0)
            # impose power limits
            if Ppos > self.max_power_charge:
                Able = 0
                Power = 0
                Current = 0
            if Pneg < self.max_power_discharge:
                Able = 0
                Power = 0
                Current = 0

        Power = Power*self.num_of_devices
        Cost = Power*self.num_of_devices
        return [Power,Cost,Able]#Power,Cost,Able

    def forecast(self, requests):
        """
        Forecast feature

        :param fleet_requests: list of fleet requests

        :return res: list of service responses
        """
        responses = []
        SOC = self.soc 

        if self.model_type == 'ERM':
            # Iterate and process each request in fleet_requests
            for req in requests:
                FleetResponse = self.run(req.P_req,req.Q_req ,req.sim_step)
                res = FleetResponse
                responses.append(res)
            # reset the model
            self.soc = SOC 
            
        elif self.model_type == 'CRM':
            PDC = self.pdc 
            IBAT = self.ibat
            VBAT = self.vbat
            V1 = self.v1
            V2 = self.v2
            VOC = self.voc 
            ES = self.es
            # Iterate and process each request in fleet_requests
            for req in requests:
                FleetResponse = self.run(req.P_req,req.Q_req,req.sim_step)
                res = FleetResponse
                responses.append(res)
            # reset the model
            self.soc = SOC 
            self.pdc = PDC
            self.ibat = IBAT
            self.vbat = VBAT
            self.v1 = V1
            self.v2 = V2
            self.voc = VOC
            self.es = ES
        else: 
            print('Error: ModelType not selected as either energy reservoir model (self), or charge reservoir model (self)')
            print('Battery-Inverter model forecast is unable to continue. In config.ini, set ModelType to self or self')

        return responses

    def change_config(self, fleet_config):
        """
        :param fleet_config: an instance of FleetConfig
        """

        # change config

        pass
