# -*- coding: utf-8 -*-
"""
Description: It contains the interface to interact with the fleet of electric 
vehicles: ElectricVehiclesFleet

Last update: 05/09/2019
Version: 1.01
Author: afernandezcanosa@anl.gov
"""
import sys
from os.path import dirname, abspath, join
sys.path.insert(0,dirname(dirname(dirname(abspath(__file__)))))

from configparser import ConfigParser
from datetime import datetime, timedelta
import numpy as np
import pandas as pd
from scipy.stats import truncnorm
import csv

from fleet_interface import FleetInterface
from fleet_response  import FleetResponse
from frequency_droop import FrequencyDroop
from fleets.electric_vehicles_fleet.load_config import LoadConfig
from utils import ensure_ddir

class ElectricVehiclesFleet(FleetInterface):
    
    def __init__(self, grid_info, ts):
        """
        Constructor
        """
        # Location of working path
        base_path = dirname(abspath(__file__))
        
        # Read config file
        config = ConfigParser()
        config.read(join(base_path, 'config.ini'))
        
        # Load config file and store data in a dataframe
        LC = LoadConfig(config)
        self.df_VehicleModels = LC.get_config_models()
        
        # Run baseline power to store baseline power and SOC if parameters 
        # of the fleet are changed. ONLY ASSIGN TRUE IF YOU CHANGE THE 
        # PARAMETERS OF THE FLEET AS IT WILL DRAMATICALLY INCREASE THE CPU TIME
        self.run_baseline = LC.get_run_baseline()
        self.n_days_base = LC.get_n_days_MC()
        # Establish the properties of the grid on which the fleet is connected on
        self.grid = grid_info
        # Number of subfleets that are going to be simulated
        self.N_SubFleets = LC.get_n_subfleets()
        # Number of vehicle models
        self.N_Models = self.df_VehicleModels.shape[0]
        # Total number of vehicles
        self.N_Vehicles = self.df_VehicleModels['Total_Vehicles'].sum()
        # Number of subfleets of each vehicle model: e.g. 1st model = 50 sub fleets, 2nd model = 25 sub fleets, ...
        self.N_VehiclesSubFleet = []
        for v in range(self.N_Models):
            self.N_VehiclesSubFleet.append(int(self.N_SubFleets*(self.df_VehicleModels['Total_Vehicles'][v]/self.N_Vehicles)))
        # Vehicles per subfleef
        self.VehiclesSubFleet = int(self.N_Vehicles/self.N_SubFleets)    
        # Assign vehicles to the array of subfleets - variable used to perform logic operations
        NL = 0; NR = 0
        self.SubFleetId = np.zeros([self.N_SubFleets,], dtype = int)
        for i in range(self.N_Models):
            NR = NR + self.N_VehiclesSubFleet[i]
            self.SubFleetId[NL:NR] = i*np.ones(self.N_VehiclesSubFleet[i])
            NL = NL + self.N_VehiclesSubFleet[i]   
            
        # Weibull distribution: From statistical studies of the NHTS survey
        self.a = LC.get_weibull_exp()               # a value of the exponent
        peak = LC.get_weibull_peak()                # Peak in 1/3 of the range
        self.lambd = peak/(((self.a-1)/self.a)**(1/self.a)) # Shape value 
        # Random seed for matching schedule and getting charging strategies
        self.seed = 0
        np.random.seed(self.seed)
        
        # Read data from NHTS survey      
        self.df_Miles     = pd.read_csv(join(base_path,'data/TRPMILES_filt.txt'), sep = '\t', header=None)
        self.df_StartTime = pd.read_csv(join(base_path,'data/STRTTIME_filt.txt'), sep = '\t', header=None)
        self.df_EndTime   = pd.read_csv(join(base_path,'data/ENDTIME_filt.txt'), sep = '\t', header=None)
        self.df_WhyTo     = pd.read_csv(join(base_path,'data/WHYTO_filt.txt' ), sep = '\t', header=None)
        
        # Percentage of cars that are charged at work/other places: Statistical studies from real data
        self.ChargedAtWork_per  = LC.get_charged_at_work_per()
        self.ChargedAtOther_per = LC.get_charged_at_other_per()

        # Initialize timestamps and local times of the class for future calculations
        self.initial_ts = ts 
        self.ts = ts
        self.initial_time = self.get_time_of_the_day(ts)
        self.time = self.get_time_of_the_day(ts)
        self.dt = 1
        
        # Mix of charging strategies: charging right away, start charging at midnight, start charging to be fully charged before the TCIN (percentage included)
        self.strategies = LC.get_charging_strategies()
        # Charging strategy corresponding to each sub fleet
        self.monitor_strategy = []
        for i in range(len(self.strategies[0])):
            self.monitor_strategy = self.monitor_strategy + [self.strategies[0][i]]*int(self.strategies[1][i]*self.N_SubFleets)
        # Randomize strategies among all the sub fleets    
        np.random.shuffle(self.monitor_strategy)
        
        # Baseline simulations
        if self.run_baseline == True:
            self.run_baseline_simulation()
        # Read the SOC curves from baseline Montecarlo simulations of the different charging strategies
        self.df_SOC_curves = pd.read_csv(join(base_path,'data/SOC_curves_charging_modes.csv' ))
        
        # Read the baseline power from Montecarlo simulations of the different charging strategies
        self.df_baseline_power = pd.read_csv(join(base_path,'data/power_baseline_charging_modes.csv' ))
        self.p_baseline = (self.strategies[1][0]*self.df_baseline_power['power_RightAway_kW'].iloc[self.initial_time] + 
                           self.strategies[1][1]*self.df_baseline_power['power_Midnight_kW'].iloc[self.initial_time] + 
                           self.strategies[1][2]*self.df_baseline_power['power_TCIN_kW'].iloc[self.initial_time])

        # Initial state of charge of all the subfleets => Depends on the baseline simulations (SOC curves)
        self.SOC = np.zeros([self.N_SubFleets,]); i = 0
        for strategy in self.monitor_strategy:
            if strategy == 'right away':
                self.SOC[i] = truncnorm.rvs(((0 - self.df_SOC_curves['SOC_mean_RightAway'][self.initial_time])/self.df_SOC_curves['SOC_std_RightAway'][self.initial_time]), 
                                            ((1 - self.df_SOC_curves['SOC_mean_RightAway'][self.initial_time])/self.df_SOC_curves['SOC_std_RightAway'][self.initial_time]), 
                                            loc = self.df_SOC_curves['SOC_mean_RightAway'][self.initial_time], scale = self.df_SOC_curves['SOC_std_RightAway'][self.initial_time], size = 1)
            elif strategy == 'midnight':
                self.SOC[i] = truncnorm.rvs(((0 - self.df_SOC_curves['SOC_mean_Midnight'][self.initial_time])/self.df_SOC_curves['SOC_std_Midnight'][self.initial_time]), 
                                            ((1 - self.df_SOC_curves['SOC_mean_Midnight'][self.initial_time])/self.df_SOC_curves['SOC_std_Midnight'][self.initial_time]), 
                                            loc = self.df_SOC_curves['SOC_mean_Midnight'][self.initial_time], scale = self.df_SOC_curves['SOC_std_Midnight'][self.initial_time], size = 1)
            else:
                self.SOC[i] = truncnorm.rvs(((0 - self.df_SOC_curves['SOC_mean_TCIN'][self.initial_time])/self.df_SOC_curves['SOC_std_TCIN'][self.initial_time]), 
                                            ((1 - self.df_SOC_curves['SOC_mean_TCIN'][self.initial_time])/self.df_SOC_curves['SOC_std_TCIN'][self.initial_time]), 
                                            loc = self.df_SOC_curves['SOC_mean_TCIN'][self.initial_time], scale = self.df_SOC_curves['SOC_std_TCIN'][self.initial_time], size = 1)
            i += 1
            
        # Calculate the voltage to calculate the range in the function to match the schedule: It is conservative to say that V = V_OC 
        self.Voltage = self.voltage_battery(self.df_VehicleModels['V_SOC_0'][self.SubFleetId],
                                            self.df_VehicleModels['V_SOC_1'][self.SubFleetId],
                                            self.df_VehicleModels['V_SOC_2'][self.SubFleetId], 
                                            self.df_VehicleModels['Number_of_cells'][self.SubFleetId],self.SOC,0,0)
        
        # Schedules of all the sub fleets
        self.ScheduleStartTime, self.ScheduleEndTime, self.ScheduleMiles, self.SchedulePurpose, self.ScheduleTotalMiles = self.match_schedule(self.seed,self.SOC,self.Voltage)
        
        # Weight used to scale the service request
        self.service_weight = LC.get_service_weight()
        
        # How to calculate effective fleet rating: this is going to be poorly
        # met because it does not consider random availability of the fleet. 
        # However this seems to be the best approximation
        self.mean_base = (self.strategies[1][0]*self.df_baseline_power['power_RightAway_kW'] + 
                          self.strategies[1][1]*self.df_baseline_power['power_Midnight_kW']  +
                          self.strategies[1][2]*self.df_baseline_power['power_TCIN_kW']).mean()
        self.mean_driven = 1 - 0.01*((self.df_VehicleModels['Total_Vehicles'] * 
                                 self.df_VehicleModels['Sitting_cars_per']).sum()/
                                 self.df_VehicleModels['Total_Vehicles'].sum())
        self.mean_charger_kW = 1e-3*((self.df_VehicleModels['Total_Vehicles'] * 
                                      self.df_VehicleModels['Max_Charger_AC_Watts']).sum()/
                                      self.df_VehicleModels['Total_Vehicles'].sum())
        self.fleet_rating = self.strategies[1][0]*self.mean_driven*self.mean_charger_kW*self.df_VehicleModels['Total_Vehicles'].sum()
        self.fleet_rating = self.fleet_rating - self.mean_base

        # How is the baseline computed and results referenced?
        self.montecarlo_reference = LC.get_base_reference()
        
        """
        Can this fleet operate in autonomous operation?
        """
        
        # Locations of the subfleets: suppose that you only have two locations
        self.location = np.random.randint(0,2,self.N_SubFleets)
        
        # Fleet configuration variables
        self.is_P_priority = LC.get_fleet_config()[0]
        self.is_autonomous = LC.get_fleet_config()[1]
        
        # Autonomous operation
        fw_21 = LC.get_FW()
        self.FW21_Enabled = fw_21[0]
        if self.FW21_Enabled == True:
            # Single-sided deadband value for low-frequency, in Hz
            self.db_UF = fw_21[1]
            # Single-sided deadband value for high-frequency, in Hz
            self.db_OF = fw_21[2]
            # Per-unit frequency change corresponding to 1 per-unit power output change (frequency droop), dimensionless
            self.k_UF  = fw_21[3]
            # Per-unit frequency change corresponding to 1 per-unit power output change (frequency droop), dimensionless
            self.k_OF  = fw_21[4]
            # Available active power, in p.u. of the DER rating
            self.P_avl = fw_21[5]
            # Minimum active power output due to DER prime mover constraints, in p.u. of the DER rating
            self.P_min = fw_21[6]
            self.P_pre = fw_21[7]
            
            # Randomization of discrete devices: deadbands must be randomize to provide a continuous response
            self.db_UF_subfleet = np.random.uniform(low = self.db_UF[0], high = self.db_UF[1], size = (self.N_SubFleets, ))
            self.db_OF_subfleet = np.random.uniform(low = self.db_OF[0], high = self.db_OF[1], size = (self.N_SubFleets, ))
        
        # Impact metrics of the fleet
        # End of life cost
        metrics = LC.get_impact_metrics_params()
        self.eol_cost = metrics[0]
        # Cylce life
        self.cycle_life = metrics[1]
        # State of health of the battery for all the subfleets
        self.soh_init = np.repeat(metrics[2], self.N_SubFleets)
        self.soh = np.repeat(metrics[2], self.N_SubFleets)
        # Energy efficiency
        self.energy_efficiency = metrics[3]
        # P_togrid/P_baseline
        self.ratio_P_togrid_P_base = 1.
        # Energy impacts of providing the grid service
        self.energy_impacts = 0.
        
    def get_time_of_the_day(self, ts):
        """ Method to calculate the time of the day in seconds to for the discharge and charge of the subfleets """
        h, m, s = ts.hour, ts.minute, ts.second
        # Convert the hours, minutes, and seconds to seconds: referenced to 4 AM
        t = int(h) * 3600 + int(m) * 60 + int(s) - 4*3600
        if t >= 0:
            return t
        else:
            return t + 24*3600
    
    def process_request(self, fleet_request):
        """
        This function takes the fleet request and repackages it for the 
        internal simulate method of the class

        :param fleet_request: an instance of FleetRequest

        :return res: an instance of FleetResponse
        """
        # call simulate method with proper inputs
        ts = fleet_request.ts_req
        dt = int(fleet_request.sim_step.total_seconds())
        start_time = fleet_request.start_time
        p_req = fleet_request.P_req
        q_req = fleet_request.Q_req
        fleet_response = self.simulate(p_req, q_req, self.SOC, self.time, dt, ts, start_time)

        return fleet_response
    
    def frequency_watt(self, p_req = 0, p_prev = 0, ts=datetime.utcnow(), location=0,
                       db_UF = 0.05, db_OF = 0.05, start_time = None):
        """
        This function takes the requested power, the previous baseline power of the device, date,
        time, location, and the deadbands for low and high frequency.
     
        :param: p_req, p_prev (base), date, location of the subfleet, deadbands
        :return p_mod: modified power of the subfleet (turn on/off for discrete fleets)
        """
        f = self.grid.get_frequency(ts,location,start_time)
        
        if f < 60 - db_UF:
            p_mod = 0
        elif f > 60 + db_OF:
            p_mod = p_req
        else:
            p_mod = p_prev
        
        return p_mod
    
    def update_soc_due_to_frequency_droop(self, initSOC, subfleet_number, p_subfleet, dt):
        """
        This method returns the modified state of charge of each subfleet 
        due to frequency droop in the grid
        """
        p_dc = self.power_dc_charger(self.df_VehicleModels['AC_Watts_Losses_0'][self.SubFleetId[subfleet_number]],
                                     self.df_VehicleModels['AC_Watts_Losses_1'][self.SubFleetId[subfleet_number]],
                                     self.df_VehicleModels['AC_Watts_Losses_2'][self.SubFleetId[subfleet_number]],
                                     self.df_VehicleModels['Max_Charger_AC_Watts'][self.SubFleetId[subfleet_number]], p_subfleet)
        R = self.resistance_battery(self.df_VehicleModels['R_SOC_0'][self.SubFleetId[subfleet_number]],
                                    self.df_VehicleModels['R_SOC_1'][self.SubFleetId[subfleet_number]],
                                    self.df_VehicleModels['R_SOC_2'][self.SubFleetId[subfleet_number]], initSOC)
        v_oc = self.voltage_battery(self.df_VehicleModels['V_SOC_0'][self.SubFleetId[subfleet_number]],
                                    self.df_VehicleModels['V_SOC_1'][self.SubFleetId[subfleet_number]],
                                    self.df_VehicleModels['V_SOC_2'][self.SubFleetId[subfleet_number]], 
                                    self.df_VehicleModels['Number_of_cells'][self.SubFleetId[subfleet_number]],initSOC,0,0)
        ibat_charging = self.current_charging(v_oc,R,p_dc) 
        Ah_rate = ibat_charging/3600
        charge_rate = Ah_rate/self.df_VehicleModels['Ah_usable'][self.SubFleetId[subfleet_number]]
        SOC_update = initSOC + charge_rate*dt
        
        if SOC_update > 1:
            p_subfleet = 0
            p_dc = 0
            SOC_update = initSOC

        return (p_subfleet*self.VehiclesSubFleet*(1 - 0.01*self.df_VehicleModels['Sitting_cars_per'][self.SubFleetId[subfleet_number]])/1000,
                SOC_update,
                p_dc*self.VehiclesSubFleet*(1 - 0.01*self.df_VehicleModels['Sitting_cars_per'][self.SubFleetId[subfleet_number]])/1000)
    
    
    def simulate(self, P_req, Q_req, initSOC, t, dt, ts, start_time):
        """ 
        Simulation part of the code: charge, discharge, ...:
        everything must be referenced to baseline power from Montecarlo 
        simulations of the different charging strategies
        """
        
        # Give the code the capability to respond to None requests
        if P_req == None:
            P_req = 0
        if Q_req == None:
            Q_req = 0

        # What is the reference? MC simulations are more accurate, but the fleet responds to None requests "randomly"
        if self.montecarlo_reference == True:
            # Baseline power is extracted from Monte Carlo simulations
            self.p_baseline = (self.strategies[1][0]*self.df_baseline_power['power_RightAway_kW'].iloc[self.time] + 
                               self.strategies[1][1]*self.df_baseline_power['power_Midnight_kW'].iloc[self.time] + 
                               self.strategies[1][2]*self.df_baseline_power['power_TCIN_kW'].iloc[self.time])
    
            # The total power requested must be referenced to the baseline power
            p_total = self.p_baseline - P_req
        else:
            # Baseline power is calculated from the current simulation
            self.p_baseline_ref_2 = 0
            p_total = self.p_baseline_ref_2 - P_req

        if any(initSOC) > 1 or any(initSOC) < 0:
            print('ERROR: initial SOC out of range')
            return [[], []]
        else:
            # SOC at the next time step
            SOC_step = np.zeros([self.N_SubFleets,])
            SOC_step[:] = initSOC[:]
            v_oc = self.voltage_battery(self.df_VehicleModels['V_SOC_0'][self.SubFleetId],
                                        self.df_VehicleModels['V_SOC_1'][self.SubFleetId],
                                        self.df_VehicleModels['V_SOC_2'][self.SubFleetId], 
                                        self.df_VehicleModels['Number_of_cells'][self.SubFleetId],initSOC,0,0)
            R = self.resistance_battery(self.df_VehicleModels['R_SOC_0'][self.SubFleetId],
                                        self.df_VehicleModels['R_SOC_1'][self.SubFleetId],
                                        self.df_VehicleModels['R_SOC_2'][self.SubFleetId], initSOC)
            
            # power of demanded by each sub fleet
            power_subfleet = np.zeros([self.N_SubFleets,])
            power_dc_subfleet = np.zeros([self.N_SubFleets,])
            for subfleet in range(self.N_SubFleets):

                # Discharge while driving
                if self.state_of_the_subfleet(t,subfleet) == 'driving':  
                    # Discharge rate for each sub fleet
                    discharge_rate = self.df_VehicleModels['Wh_mi'][self.SubFleetId[subfleet]]/(v_oc.iloc[subfleet]*self.df_VehicleModels['Ah_usable'][self.SubFleetId[subfleet]])
                    trip_id  = self.trip_identification(t,subfleet)
                    avg_speed = self.average_speed_of_trip_miles_per_second(subfleet, trip_id)
                    SOC_step[subfleet] = initSOC[subfleet] - discharge_rate*avg_speed*dt
                    power_subfleet[subfleet] = 0
                    # Power DC of each sub fleet to calculate charging efficiency
                    power_dc_subfleet[subfleet] = 0
                                      
                # Certain amount of the vehicles of each sub fleet are charged at work: real data -> uncontrolled charging
                elif self.state_of_the_subfleet(t,subfleet) == 'work':
                    power_ac = self.df_VehicleModels['Max_Charger_AC_Watts'][self.SubFleetId[subfleet]]
                    power_dc = self.power_dc_charger(self.df_VehicleModels['AC_Watts_Losses_0'][self.SubFleetId[subfleet]],
                                                     self.df_VehicleModels['AC_Watts_Losses_1'][self.SubFleetId[subfleet]],
                                                     self.df_VehicleModels['AC_Watts_Losses_2'][self.SubFleetId[subfleet]],
                                                     self.df_VehicleModels['Max_Charger_AC_Watts'][self.SubFleetId[subfleet]],power_ac)
                    ibat_charging = self.current_charging(v_oc.iloc[subfleet],R.iloc[subfleet],power_dc) 
                    Ah_rate = ibat_charging/3600
                    charge_rate = Ah_rate/self.df_VehicleModels['Ah_usable'][self.SubFleetId[subfleet]]
                    
                    # State of charge at the next time step and power of the subfleet
                    SOC_step[subfleet] = initSOC[subfleet] + charge_rate*self.ChargedAtWork_per*dt
                    power_subfleet[subfleet] = power_ac*self.ChargedAtWork_per*self.VehiclesSubFleet*(1 - 0.01*self.df_VehicleModels['Sitting_cars_per'][self.SubFleetId[subfleet]])/1000
                    # Power DC of each sub fleet to calculate charging efficiency
                    power_dc_subfleet[subfleet] = power_dc*self.ChargedAtWork_per*self.VehiclesSubFleet*(1 - 0.01*self.df_VehicleModels['Sitting_cars_per'][self.SubFleetId[subfleet]])/1000
                    # Check if the subfleet is fully charged
                    if SOC_step[subfleet] > 1:
                        SOC_step[subfleet] = initSOC[subfleet]
                        power_subfleet[subfleet] = 0
                        power_dc_subfleet[subfleet] = 0
                    
                # Certain amount of the vehicles of each sub fleet are charged at other places: grocery stores, restaurants, etc -> uncontrolled charging
                elif self.state_of_the_subfleet(t,subfleet) == 'other':
                    power_ac = self.df_VehicleModels['Max_Charger_AC_Watts'][self.SubFleetId[subfleet]]
                    power_dc = self.power_dc_charger(self.df_VehicleModels['AC_Watts_Losses_0'][self.SubFleetId[subfleet]],
                                                     self.df_VehicleModels['AC_Watts_Losses_1'][self.SubFleetId[subfleet]],
                                                     self.df_VehicleModels['AC_Watts_Losses_2'][self.SubFleetId[subfleet]],
                                                     self.df_VehicleModels['Max_Charger_AC_Watts'][self.SubFleetId[subfleet]],power_ac)
                    ibat_charging = self.current_charging(v_oc.iloc[subfleet],R.iloc[subfleet],power_dc) 
                    Ah_rate = ibat_charging/3600
                    charge_rate = Ah_rate/self.df_VehicleModels['Ah_usable'][self.SubFleetId[subfleet]]
                    
                    # State of charge at the next time step and power of the subfleet
                    SOC_step[subfleet] = initSOC[subfleet] + charge_rate*self.ChargedAtOther_per*dt
                    power_subfleet[subfleet] = power_ac*self.ChargedAtOther_per*self.VehiclesSubFleet*(1 - 0.01*self.df_VehicleModels['Sitting_cars_per'][self.SubFleetId[subfleet]])/1000
                    power_dc_subfleet[subfleet] = power_dc*self.ChargedAtOther_per*self.VehiclesSubFleet*(1 - 0.01*self.df_VehicleModels['Sitting_cars_per'][self.SubFleetId[subfleet]])/1000
                    # Check if the subfleet is fully charged
                    if SOC_step[subfleet] > 1:
                        SOC_step[subfleet] = initSOC[subfleet]
                        power_subfleet[subfleet] = 0
                        power_dc_subfleet[subfleet] = 0
                    
                # Hypothesis: the sub fleets are only charged at home during night or right away not in these "stops"
                elif self.state_of_the_subfleet(t,subfleet) == 'home':
                    power_subfleet[subfleet] = 0
                    power_dc_subfleet[subfleet] = 0
                    
                # Charging at home after all-day trips with different charging strategies
                elif self.state_of_the_subfleet(t,subfleet) == 'home after schedule':  
                    if self.monitor_strategy[subfleet] == 'midnight':     # subfleets that start charging at midnight -> uncontrolled case
                        # time to start charging: usually at 12 AM (20*3600), but earlier may be required for some cases depending on the case
                        start_charging = 20*3600
                        SOC_step[subfleet], power_subfleet[subfleet], power_dc_subfleet[subfleet] = self.start_charging_midnight_strategy(start_charging, t, subfleet, initSOC[subfleet], dt)
                        # Check if the subfleet is fully charged
                        if SOC_step[subfleet] > 1:
                            SOC_step[subfleet] = initSOC[subfleet]
                            power_subfleet[subfleet] = 0
                            power_dc_subfleet[subfleet] = 0
                    
                    elif self.monitor_strategy[subfleet] == 'tcin':      # subfleets that start charging at a certain time to be fully charged before the tcin
                        # time to be fully charged at the next day or the current day depending on the actual time
                        if t < self.ScheduleStartTime.iloc[subfleet][1]:
                            tcin = self.ScheduleStartTime.iloc[subfleet][1]
                        else:
                            tcin = self.ScheduleStartTime.iloc[subfleet][1] + 24*3600
                        SOC_step[subfleet], power_subfleet[subfleet],_,power_dc_subfleet[subfleet] = self.start_charging_to_meet_tcin(tcin, t, subfleet, initSOC[subfleet], dt)
                        # Check if the subfleet is fully charged
                        if SOC_step[subfleet] > 1:
                            SOC_step[subfleet] = initSOC[subfleet]
                            power_subfleet[subfleet] = 0
                            power_dc_subfleet[subfleet] = 0           
            # Calculate the total power uncontrolled            
            power_uncontrolled = np.sum(power_subfleet, axis = 0)
            
            # We can reference all the calculations to the real baseline of the case that is being run
            if self.montecarlo_reference == False:
                self.p_baseline_ref_2 = power_uncontrolled
                
                # Calculate new baseline
                for subfleet in range(self.N_SubFleets):
                    if self.state_of_the_subfleet(t,subfleet) == 'home after schedule':  
                        if self.monitor_strategy[subfleet] == 'right away':
                            SOC_check, p,_ = self.start_charging_right_away_strategy(subfleet, initSOC[subfleet], dt)
                            if SOC_check <= 1:
                                self.p_baseline_ref_2 += p
                # New power demanded                
                p_total = self.p_baseline_ref_2 - P_req

            SOC_monitor = pd.DataFrame(columns = ['SOCinit', 'state_subfleet', 'charging_strategy'])
            for subfleet in range(self.N_SubFleets):
                SOC_monitor.loc[subfleet, 'SOCinit'] = initSOC[subfleet]
                SOC_monitor.loc[subfleet, 'state_subfleet'] = self.state_of_the_subfleet(t,subfleet)
                SOC_monitor.loc[subfleet, 'charging_strategy'] = self.monitor_strategy[subfleet]
            
            # Sort the state of charge to charge the vehicles in the right away charging strategy
            SOC_sorted = SOC_monitor.sort_values('SOCinit')
                
            # Controlled case: the controlled case + the uncontrolled case must be equal to the requested power
            # Start charging the electric vehicles with the lowest state of charge
            power_controlled_thres = p_total - power_uncontrolled
            power_controlled = 0
            for subfleet in range(self.N_SubFleets):
                idx = SOC_sorted['state_subfleet'].index[subfleet]
                if SOC_sorted['state_subfleet'][idx] == 'home after schedule':
                    if SOC_sorted['charging_strategy'][idx] == 'right away':  # subfleets that start charging immediately -> controlled charging
                        # Check the time to start charging to meet tcin
                        if t < self.ScheduleStartTime.iloc[idx][1]:
                            tcin = self.ScheduleStartTime.iloc[idx][1]
                        else:
                            tcin = self.ScheduleStartTime.iloc[idx][1] + 24*3600
                        _,_,check_tcin,_ = self.start_charging_to_meet_tcin(tcin, t, idx, initSOC[idx], dt)
                        # If the time is less than the time when the car must be start charging to meet tcin then:
                        if t < check_tcin:
                            if power_uncontrolled >= p_total: 
                                power_demanded = power_uncontrolled  # All the right away chargers turned off
                            else:
                                SOC_step[idx], power_subfleet[idx], power_dc_subfleet[idx] = self.start_charging_right_away_strategy(idx, SOC_sorted['SOCinit'][idx], dt)
                                # Check if the subfleet is fully charged
                                if SOC_step[idx] > 1:
                                    SOC_step[idx] = initSOC[idx]
                                    power_subfleet[idx] = 0
                                    power_dc_subfleet[idx] = 0
                                # Check if the controlled power is greater than our constraint
                                elif (power_controlled + power_subfleet[idx]) < power_controlled_thres:
                                    power_controlled += power_subfleet[idx]
                                else:
                                    # Surpasses the maximum power and returns the previous state
                                    power_subfleet[idx] = 0
                                    power_dc_subfleet[idx] = 0
                                    SOC_step[idx] = initSOC[idx]
                        # However, if the time is greater, we have to start charging right away regardless the service demanded (constraint of the device)
                        elif t >= check_tcin:
                            SOC_step[idx], power_subfleet[idx], power_dc_subfleet[idx] = self.start_charging_right_away_strategy(idx, SOC_sorted['SOCinit'][idx], dt)
                            power_controlled += power_subfleet[idx]   
                            # Check if the subfleet is fully charged
                            if SOC_step[idx] > 1:
                                SOC_step[idx] = initSOC[idx]
                                power_subfleet[idx] = 0
                                power_dc_subfleet[idx] = 0
            
            """
            Modify the power and SOC of the different subfeets according 
            to the frequency droop regulation according to IEEE standard
            """
            for subfleet in range(self.N_SubFleets):
                if self.state_of_the_subfleet(t,subfleet) == 'home after schedule':
                    if self.FW21_Enabled and self.is_autonomous:
                        power_ac = self.df_VehicleModels['Max_Charger_AC_Watts'][self.SubFleetId[subfleet]]
                        p_prev = power_subfleet[subfleet]*1000/(self.VehiclesSubFleet*(1 - 0.01*self.df_VehicleModels['Sitting_cars_per'][self.SubFleetId[subfleet]]))
                        power_subfleet[subfleet] = self.frequency_watt(power_ac,
                                                                       p_prev,
                                                                       self.ts,
                                                                       self.location[subfleet],
                                                                       self.db_UF_subfleet[subfleet],
                                                                       self.db_OF_subfleet[subfleet],
                                                                       start_time)
                        (power_subfleet[subfleet],
                         SOC_step[subfleet],
                         power_dc_subfleet[subfleet]) = self.update_soc_due_to_frequency_droop(initSOC[subfleet],
                                                                                               subfleet,
                                                                                               power_subfleet[subfleet],
                                                                                               dt)
                    else:
                        break

            # Demand of power
            power_demanded = np.sum(power_subfleet, axis = 0)
            power_dc_demanded = np.sum(power_dc_subfleet, axis = 0)
            
            # Calculate maximum power that can be injected to the grid -> all the right away chargers are turned on
            for subfleet in range(self.N_SubFleets):
                if self.state_of_the_subfleet(t,subfleet) == 'home after schedule':  
                    if self.monitor_strategy[subfleet] == 'right away':
                        SOC_check, power_subfleet[subfleet],_ = self.start_charging_right_away_strategy(subfleet, initSOC[subfleet], dt)
                        if SOC_check > 1:
                            power_subfleet[subfleet] = 0
            # Maximum demand of power
            max_power_demanded = np.sum(power_subfleet, axis = 0)
            
            # Calculate the energy stored in each individual subfleet
            total_energy = 0
            total_capacity = 0
            energy_per_subfleet = np.zeros([self.N_SubFleets,])
            for subfleet in range(self.N_SubFleets):
                R = self.resistance_battery(self.df_VehicleModels['R_SOC_0'][self.SubFleetId[subfleet]],
                                            self.df_VehicleModels['R_SOC_1'][self.SubFleetId[subfleet]],
                                            self.df_VehicleModels['R_SOC_2'][self.SubFleetId[subfleet]], SOC_step[subfleet])
                v_oc = self.voltage_battery(self.df_VehicleModels['V_SOC_0'][self.SubFleetId[subfleet]],
                                            self.df_VehicleModels['V_SOC_1'][self.SubFleetId[subfleet]],
                                            self.df_VehicleModels['V_SOC_2'][self.SubFleetId[subfleet]], 
                                            self.df_VehicleModels['Number_of_cells'][self.SubFleetId[subfleet]],SOC_step[subfleet],0,0)
                p_dc = self.power_dc_charger(self.df_VehicleModels['AC_Watts_Losses_0'][self.SubFleetId[subfleet]],
                                             self.df_VehicleModels['AC_Watts_Losses_1'][self.SubFleetId[subfleet]],
                                             self.df_VehicleModels['AC_Watts_Losses_2'][self.SubFleetId[subfleet]],
                                             self.df_VehicleModels['Max_Charger_AC_Watts'][self.SubFleetId[subfleet]],power_subfleet[subfleet])
                ibat = self.current_charging(v_oc,R,p_dc)
                v = self.voltage_battery(self.df_VehicleModels['V_SOC_0'][self.SubFleetId[subfleet]],
                                         self.df_VehicleModels['V_SOC_1'][self.SubFleetId[subfleet]],
                                         self.df_VehicleModels['V_SOC_2'][self.SubFleetId[subfleet]], 
                                         self.df_VehicleModels['Number_of_cells'][self.SubFleetId[subfleet]],SOC_step[subfleet],R,ibat)
                capacity = self.df_VehicleModels['Ah_usable'][self.SubFleetId[subfleet]]
                # Energy per sub fleet and total energy
                energy_per_subfleet[subfleet] = self.energy_stored_per_subfleet(SOC_step[subfleet], capacity, v, self.VehiclesSubFleet)
                total_energy += energy_per_subfleet[subfleet]
                # Total Capacity
                total_capacity += self.energy_stored_per_subfleet(1, capacity, v, self.VehiclesSubFleet)
            
            # response outputs 
            response = FleetResponse()
            
            if self.montecarlo_reference == False:
                self.p_baseline = self.p_baseline_ref_2
            
            response.ts = ts
            response.sim_step  = timedelta(seconds=dt)
            response.P_togrid  = - power_demanded
            response.Q_togrid  = 0
            response.P_service = - (power_demanded - self.p_baseline)
            response.Q_service = 0
            response.P_base    = - self.p_baseline
            response.Q_base    = 0
            
            response.E = total_energy
            response.C = total_capacity
            
            response.P_togrid_min = - max_power_demanded
            response.P_togrid_max = - power_controlled
            response.Q_togrid_max = 0
            response.Q_togrid_min = 0
            
            response.P_service_min = - (max_power_demanded - self.p_baseline)
            response.P_service_max = - (power_controlled - self.p_baseline) 
            response.Q_service_max = 0
            response.Q_service_min = 0
            
            response.P_dot_up   = 0
            response.P_dot_down = 0
            response.Q_dot_up   = 0
            response.Q_dot_down = 0
                   
            if power_demanded == 0:
                response.Eff_charge = 0
            else:
                response.Eff_charge = (power_dc_demanded*dt)/(power_demanded*dt)*100                      
            response.Eff_discharge = 1

            response.dT_hold_limit = None
            response.T_restore     = None
            
            # TODO: Get SOC_cost and Strike_price API variables not constant over time
            response.SOC_cost     = 0.2
            # TODO: Conversion from SOC_cost to Strike_price from "Estimating a DER Device's Strike Price Corresponding..."
            delta_t = 1
            response.Strike_price = 0.5*(response.SOC_cost*delta_t/response.C)
            
            self.SOC = SOC_step
            self.time = t + dt
            self.ts = self.ts + timedelta(seconds = dt)
            # Restart time if it surpasses 24 hours
            if self.time > 24*3600:
                self.time = self.time - 24*3600
                
            # Impact Metrics    
            # Update the state of health of the batteries of each subfleet
            for subfleet in range(self.N_SubFleets):
                self.soh[subfleet] = (self.soh[subfleet] - 
                                100*(dt/3600)*abs(power_subfleet[subfleet]) / 
                                ((1+1/self.energy_efficiency)*self.cycle_life*energy_per_subfleet[subfleet]))
            
            self.ratio_P_togrid_P_base = response.P_togrid/(-self.p_baseline)
            self.energy_impacts += abs(response.P_service)*(dt/3600)
            
            # Check the outputs
            return response
    
    def forecast(self, requests):
        """
        Request for current timestep

        :param requests: list of  requests

        :return res: list of FleetResponse
        """
        
        SOC_aux = self.SOC
        responses = []
        
        for req in requests:
            ts = req.ts_req
            dt = int(req.sim_step.total_seconds())
            p_req = req.P_req
            q_req = req.Q_req
            start_time = req.start_time
            res = self.simulate(p_req, q_req, self.SOC, self.time, dt, ts, start_time)
            responses.append(res)     
        # restart the state of charge
        self.SOC = SOC_aux
        
        return responses
    
    def state_of_the_subfleet(self,t_secs,subfleet_number):
        """ Method to specify the state of the subfleet: driving, work, other, home after schedule, home """
        if t_secs > max(self.ScheduleEndTime.iloc[subfleet_number]) or t_secs < self.ScheduleStartTime.iloc[subfleet_number][1]:
            return 'home after schedule'
        else:
            for i in range(np.min(np.shape(self.SchedulePurpose.iloc[subfleet_number]))): 
                if t_secs < self.ScheduleEndTime.iloc[subfleet_number][i+1] and t_secs > self.ScheduleStartTime.iloc[subfleet_number][i+1]:
                    return 'driving' 
                elif self.SchedulePurpose.iloc[subfleet_number][i+1] == 2 and t_secs < self.ScheduleStartTime.iloc[subfleet_number][i+2]: 
                    return 'work'
                elif self.SchedulePurpose.iloc[subfleet_number][i+1] == 1.5 and t_secs < self.ScheduleStartTime.iloc[subfleet_number][i+2]: 
                    return 'other'
                elif self.SchedulePurpose.iloc[subfleet_number][i+1] == 1.0 and t_secs < self.ScheduleStartTime.iloc[subfleet_number][i+2]: 
                    return 'home'
                      
    def trip_identification(self,t_secs,subfleet_number):
        """ Method to identify the trip of the day and returns the trip id """
        for trip_id in range(np.min(np.shape(self.SchedulePurpose.iloc[subfleet_number]))): 
            if t_secs < self.ScheduleEndTime.iloc[subfleet_number][trip_id+1] and t_secs > self.ScheduleStartTime.iloc[subfleet_number][trip_id+1]:
                return trip_id
            
    def average_speed_of_trip_miles_per_second(self,subfleet_number,trip_id):
        """ average speed of the trip expressed in miles per second """
        t = self.ScheduleEndTime.iloc[subfleet_number][trip_id+1] - self.ScheduleStartTime.iloc[subfleet_number][trip_id+1]
        miles = self.ScheduleMiles.iloc[subfleet_number][trip_id+1]
        return miles/t

    def voltage_battery(self,v0,v1,v2,cells,SOC,R,current_bat):
        """ Voltage as a function of the State of Charge of the battery, the resistance, and the current"""
        return cells*(v0 + v1*SOC + v2*SOC**2 + R*current_bat)
    
    def resistance_battery(self,r0,r1,r2,SOC):
        """ Resistance as a function of the State of Charge of the battery """
        return r0 + r1*SOC + r2*SOC**2

    def range_subfleet(self,Ah_usable,Voltage, Wh_mi, SOC):
        """ Method to calculate the range for a given electric vehicle model """
        return SOC*Ah_usable*Voltage/Wh_mi
    
    def power_dc_charger(self, a0, a1, a2, power_ac_max, power_ac):
        """ Method to calculate DC power in the charger as a function of the losses and the maximum AC power of the charger """
        if power_ac < power_ac_max:
            return power_ac - (a0 + a1*power_ac + a2*power_ac**2)
        else:
            return power_ac_max - (a0 + a1*power_ac_max + a2*power_ac_max**2)
        
    def current_charging(self,v_oc,R,power_dc):
        """ Method to calculate the current to charge the battery as a function of the V_OC, P_DC, internal resistance of the battery """
        return (v_oc - np.sqrt(v_oc**2 - 4*R*power_dc))/(2.*R)   
    
    def energy_stored_per_subfleet(self, SOC, v, Ah_nom, n_vehicles_subfleet):
        """ Method to calculate energy stored of each sub fleet """
        return SOC*Ah_nom*v*n_vehicles_subfleet/1000
        
    def match_schedule(self, seed, SOC, V):
        """ Method to match the schedule of each sub fleet from NHTS data"""
        
        #fix pseudorandom numbers
        np.random.seed(seed)
        
        # Daily range of each subfleet based on the Weibull distribution and the features of the vehicle models
        SubFleetRange = self.range_subfleet(self.df_VehicleModels['Ah_usable'][self.SubFleetId],V,
                                            self.df_VehicleModels['Wh_mi'][self.SubFleetId],SOC)*self.lambd*np.random.weibull(self.a,self.N_SubFleets)
        # Daily range from the NHTS survey
        Miles = self.df_Miles.drop(self.df_Miles.columns[0], axis = 1)
        NHTS_DailyRange = Miles.sum(axis = 1)
        
        # Matching the Schedule
        # Assign the Range of each subfleet
        idx = np.zeros([self.N_SubFleets,], dtype = int)
        for i in range(self.N_SubFleets):
            idx[i] = (NHTS_DailyRange - SubFleetRange.iloc[i]).abs().idxmin()
        # Remove the first column of each dataset      
        StartTime = self.df_StartTime.drop(self.df_StartTime.columns[0], axis = 1)
        EndTime   = self.df_EndTime.drop(self.df_EndTime.columns[0], axis = 1)
        WhyTo     = self.df_WhyTo.drop(self.df_WhyTo.columns[0], axis = 1).iloc[idx]
        Miles     = Miles.iloc[idx]
        # Transform the times into seconds and substitute negative values by 0: referenced to 4 AM
        StartTime_secs = ((StartTime.iloc[idx] - 400)/100)*3600
        EndTime_secs   = ((EndTime.iloc[idx] - 400)/100)*3600
        StartTime_secs = StartTime_secs.mask(StartTime_secs < 0, 0)
        EndTime_secs   = EndTime_secs.mask(EndTime_secs < 0, 0)
    
        # Miles per each subfleet
        MilesSubfleet = NHTS_DailyRange.iloc[idx]
    
        # Purpose of the travel: 1 is at home, 2 is at work, 1.5 is other 
        Purpose = WhyTo.replace(to_replace = [1, 11, 13], value = [1, 2, 2])
        Purpose = Purpose.mask(Purpose > 11, 1.5)
    
        return StartTime_secs, EndTime_secs, Miles, Purpose, MilesSubfleet
       
    def start_charging_midnight_strategy(self, charge_programmed, t_secs, subfleet_number, SOC, dt):
        """ Method to calculate the start-charging-at-midnight strategy """
        if t_secs >= charge_programmed:
            v = self.voltage_battery(self.df_VehicleModels['V_SOC_0'][self.SubFleetId[subfleet_number]],
                                     self.df_VehicleModels['V_SOC_1'][self.SubFleetId[subfleet_number]],
                                     self.df_VehicleModels['V_SOC_2'][self.SubFleetId[subfleet_number]], 
                                     self.df_VehicleModels['Number_of_cells'][self.SubFleetId[subfleet_number]],SOC,0,0)
            R = self.resistance_battery(self.df_VehicleModels['R_SOC_0'][self.SubFleetId[subfleet_number]],
                                        self.df_VehicleModels['R_SOC_1'][self.SubFleetId[subfleet_number]],
                                        self.df_VehicleModels['R_SOC_2'][self.SubFleetId[subfleet_number]], SOC)
            power_ac = self.df_VehicleModels['Max_Charger_AC_Watts'][self.SubFleetId[subfleet_number]]
            power_dc = self.power_dc_charger(self.df_VehicleModels['AC_Watts_Losses_0'][self.SubFleetId[subfleet_number]],
                                             self.df_VehicleModels['AC_Watts_Losses_1'][self.SubFleetId[subfleet_number]],
                                             self.df_VehicleModels['AC_Watts_Losses_2'][self.SubFleetId[subfleet_number]],
                                             self.df_VehicleModels['Max_Charger_AC_Watts'][self.SubFleetId[subfleet_number]],power_ac)
            ibat_charging = self.current_charging(v,R,power_dc) 
            Ah_rate = ibat_charging/3600
            charge_rate = Ah_rate/self.df_VehicleModels['Ah_usable'][self.SubFleetId[subfleet_number]]
            SOC_step = SOC + charge_rate*dt
            
            return (SOC_step,
                    power_ac*self.VehiclesSubFleet*(1 - 0.01*self.df_VehicleModels['Sitting_cars_per'][self.SubFleetId[subfleet_number]])/1000,
                    power_dc*self.VehiclesSubFleet*(1 - 0.01*self.df_VehicleModels['Sitting_cars_per'][self.SubFleetId[subfleet_number]])/1000)
        else:
            return SOC, 0, 0
        
    def start_charging_to_meet_tcin(self, tcin, t_secs, subfleet_number, SOC, dt):
        """ Method to calculate the start-charging-to-be-fully-charged strategy """
        # This can be different for more complicated models
        hours_before = 1
        time_fully_charged = tcin - hours_before*3600
        
        v = self.voltage_battery(self.df_VehicleModels['V_SOC_0'][self.SubFleetId[subfleet_number]],
                                 self.df_VehicleModels['V_SOC_1'][self.SubFleetId[subfleet_number]],
                                 self.df_VehicleModels['V_SOC_2'][self.SubFleetId[subfleet_number]], 
                                 self.df_VehicleModels['Number_of_cells'][self.SubFleetId[subfleet_number]],SOC,0,0)
        R = self.resistance_battery(self.df_VehicleModels['R_SOC_0'][self.SubFleetId[subfleet_number]],
                                    self.df_VehicleModels['R_SOC_1'][self.SubFleetId[subfleet_number]],
                                    self.df_VehicleModels['R_SOC_2'][self.SubFleetId[subfleet_number]], SOC)
        power_ac = self.df_VehicleModels['Max_Charger_AC_Watts'][self.SubFleetId[subfleet_number]]
        power_dc = self.power_dc_charger(self.df_VehicleModels['AC_Watts_Losses_0'][self.SubFleetId[subfleet_number]],
                                         self.df_VehicleModels['AC_Watts_Losses_1'][self.SubFleetId[subfleet_number]],
                                         self.df_VehicleModels['AC_Watts_Losses_2'][self.SubFleetId[subfleet_number]],
                                         self.df_VehicleModels['Max_Charger_AC_Watts'][self.SubFleetId[subfleet_number]],power_ac)
        ibat_charging = self.current_charging(v,R,power_dc) 
        Ah_rate = ibat_charging/3600
        charge_rate = Ah_rate/self.df_VehicleModels['Ah_usable'][self.SubFleetId[subfleet_number]]
        
        # Calculate that the car should start charging to be fully charged certain time before the tcin
        delta_SOC = 1 - SOC
        time_start_charging = int(time_fully_charged - (delta_SOC/charge_rate))
        
        if t_secs >= time_start_charging:
            SOC_step = SOC + charge_rate*dt
            return (SOC_step,
                    power_ac*self.VehiclesSubFleet*(1 - 0.01*self.df_VehicleModels['Sitting_cars_per'][self.SubFleetId[subfleet_number]])/1000,
                    time_start_charging,
                    power_dc*self.VehiclesSubFleet*(1 - 0.01*self.df_VehicleModels['Sitting_cars_per'][self.SubFleetId[subfleet_number]])/1000)
        else:
            return SOC, 0, time_start_charging, 0
        
    def start_charging_right_away_strategy(self, subfleet_number, SOC, dt):
        """ 
        Method to calculate the start-charging-right-away strategy
        """
        v = self.voltage_battery(self.df_VehicleModels['V_SOC_0'][self.SubFleetId[subfleet_number]],
                                 self.df_VehicleModels['V_SOC_1'][self.SubFleetId[subfleet_number]],
                                 self.df_VehicleModels['V_SOC_2'][self.SubFleetId[subfleet_number]], 
                                 self.df_VehicleModels['Number_of_cells'][self.SubFleetId[subfleet_number]],SOC,0,0)
        R = self.resistance_battery(self.df_VehicleModels['R_SOC_0'][self.SubFleetId[subfleet_number]],
                                    self.df_VehicleModels['R_SOC_1'][self.SubFleetId[subfleet_number]],
                                    self.df_VehicleModels['R_SOC_2'][self.SubFleetId[subfleet_number]], SOC)
        power_ac = self.df_VehicleModels['Max_Charger_AC_Watts'][self.SubFleetId[subfleet_number]]
        power_dc = self.power_dc_charger(self.df_VehicleModels['AC_Watts_Losses_0'][self.SubFleetId[subfleet_number]],
                                         self.df_VehicleModels['AC_Watts_Losses_1'][self.SubFleetId[subfleet_number]],
                                         self.df_VehicleModels['AC_Watts_Losses_2'][self.SubFleetId[subfleet_number]],
                                         self.df_VehicleModels['Max_Charger_AC_Watts'][self.SubFleetId[subfleet_number]],power_ac)
        ibat_charging = self.current_charging(v,R,power_dc) 
        Ah_rate = ibat_charging/3600
        charge_rate = Ah_rate/self.df_VehicleModels['Ah_usable'][self.SubFleetId[subfleet_number]]
        SOC_step = SOC + charge_rate*dt
        
        return (SOC_step,
                power_ac*self.VehiclesSubFleet*(1 - 0.01*self.df_VehicleModels['Sitting_cars_per'][self.SubFleetId[subfleet_number]])/1000,
                power_dc*self.VehiclesSubFleet*(1 - 0.01*self.df_VehicleModels['Sitting_cars_per'][self.SubFleetId[subfleet_number]])/1000)
    

    def run_baseline_simulation(self):
        """ 
        Method to run baseline simulation and store power level and SOC of 
        the sub fleets.
        """
        n_days_base = self.n_days_base
        sim_time = 24*3600
        
        print("Running baseline simulation ...")       
        print("Running baseline right away charging strategy ...")
        soc_1, power_base_1, soc_std_1 = self.run_baseline_right_away(n_days_base, sim_time)
        
        print("Running baseline midnight charging strategy ...")
        soc_2, power_base_2, soc_std_2 = self.run_baseline_midnight(n_days_base, sim_time)
        
        print("Running baseline tcin charging strategy ... ")
        soc_3, power_base_3, soc_std_3 = self.run_baseline_tcin(n_days_base, sim_time)
       
        print("Exporting baseline soc and power ...")
        # Dataframe to import the initial soc of the sub fleets with the aim to initialize the class
        data_soc = {'time': np.linspace(0,sim_time-1,sim_time),
                    'SOC_mean_RightAway': soc_1, 'SOC_std_RightAway': soc_std_1,
                    'SOC_mean_Midnight': soc_2, 'SOC_std_Midnight': soc_std_2,
                    'SOC_mean_TCIN': soc_3, 'SOC_std_TCIN': soc_std_3}           
        df_soc = pd.DataFrame(data=data_soc, columns=['time',
                                                      'SOC_mean_RightAway', 'SOC_std_RightAway',
                                                      'SOC_mean_Midnight', 'SOC_std_Midnight',
                                                      'SOC_mean_TCIN', 'SOC_std_TCIN'])   
        
        df_soc[['SOC_std_RightAway', 'SOC_std_Midnight', 'SOC_std_TCIN']] = \
        df_soc[['SOC_std_RightAway', 'SOC_std_Midnight', 'SOC_std_TCIN']].replace(0,1e-4)

        # Dataframe to import the baseline power with the aim to provide service power
        data_power = {'time': np.linspace(0,2*sim_time-1,2*sim_time),
                           'power_RightAway_kW': np.hstack((power_base_1*1e-3, power_base_1*1e-3)),
                           'power_Midnight_kW': np.hstack((power_base_2*1e-3, power_base_2*1e-3)),
                           'power_TCIN_kW': np.hstack((power_base_3*1e-3, power_base_3*1e-3))}            
        df_power = pd.DataFrame(data = data_power, columns = ['time', 
                                                              'power_RightAway_kW',
                                                              'power_Midnight_kW',
                                                              'power_TCIN_kW'])
        base_path = dirname(abspath(__file__))
        path = join(base_path,'data')
        
        df_soc.to_csv(join(path, r'SOC_curves_charging_modes.csv'), index = False)
        df_power.to_csv(join(path, r'power_baseline_charging_modes.csv'), index = False)
        print("Exported")
        
    def discharge_baseline(self, StartTime_secs, EndTime_secs, Miles, Purpose, MilesSubfleet, SOC, SOC_sf, sim_time, power_ac, v):
        """ Method to compute discharging for the baseline case """
        power_ac_demanded = np.zeros([self.N_SubFleets,sim_time])
        rate_dis = np.array(self.df_VehicleModels['Wh_mi'][self.SubFleetId]/(v*self.df_VehicleModels['Ah_usable'][self.SubFleetId]))
        j_full_charge = np.zeros([self.N_SubFleets,], dtype = int)
        time_full_charge = np.zeros([self.N_SubFleets,], dtype = int)
        SOC_time = np.zeros([self.N_SubFleets, sim_time])
        
        for i in range(self.N_SubFleets):
            SOC_time[i][0:int(StartTime_secs.iloc[i][1])] = SOC[i]
            for k in range(np.min(np.shape(Purpose.iloc[i]))):
                if Purpose.iloc[i][k+1] > 0:
                    # Sub fleet is driving
                    t1 = int(EndTime_secs.iloc[i][k+1]) - int(StartTime_secs.iloc[i][k+1])
                    if t1 <= 0:
                        t1 = 1
                    # Discharging
                    SOC_time[i][int(StartTime_secs.iloc[i][k+1]):int(EndTime_secs.iloc[i][k+1])] = np.linspace(SOC[i], SOC[i]-rate_dis[i]*Miles.iloc[i][k+1], t1)
                    SOC_sf[i] = SOC_sf[i] - rate_dis[i]*Miles.iloc[i][k+1]
                    power_dc = self.power_dc_charger(self.df_VehicleModels['AC_Watts_Losses_0'][self.SubFleetId[i]],
                                                     self.df_VehicleModels['AC_Watts_Losses_1'][self.SubFleetId[i]],
                                                     self.df_VehicleModels['AC_Watts_Losses_2'][self.SubFleetId[i]],
                                                     self.df_VehicleModels['Max_Charger_AC_Watts'][self.SubFleetId[i]],
                                                     power_ac.iloc[i])
                    v_oc = self.voltage_battery(self.df_VehicleModels['V_SOC_0'][self.SubFleetId[i]],
                                                self.df_VehicleModels['V_SOC_1'][self.SubFleetId[i]],
                                                self.df_VehicleModels['V_SOC_2'][self.SubFleetId[i]], 
                                                self.df_VehicleModels['Number_of_cells'][self.SubFleetId[i]], SOC_time[i][int(EndTime_secs.iloc[i][k+1])], 0, 0)       
                    r_batt = self.resistance_battery(self.df_VehicleModels['R_SOC_0'][self.SubFleetId[i]],
                                                     self.df_VehicleModels['R_SOC_1'][self.SubFleetId[i]],
                                                     self.df_VehicleModels['R_SOC_2'][self.SubFleetId[i]], SOC_time[i][int(EndTime_secs.iloc[i][k+1])])            
                    i_batt = self.current_charging(v_oc,r_batt,power_dc)
                    Ah_rate = i_batt/3600
                    charging_rate = Ah_rate/self.df_VehicleModels['Ah_usable'][self.SubFleetId[i]]                        
                    # Charging at work
                    if Purpose.iloc[i][k+1] == 2:
                        t = int(StartTime_secs.iloc[i][k+2]) - int(EndTime_secs.iloc[i][k+1])
                        SOC_time[i][int(EndTime_secs.iloc[i][k+1]):int(StartTime_secs.iloc[i][k+2])] = np.linspace(SOC_sf[i],
                                SOC_sf[i] + self.ChargedAtWork_per*charging_rate*t, t)
                        if any(SOC_time[i][int(EndTime_secs.iloc[i][k+1]):int(StartTime_secs.iloc[i][k+2])] >= 1):
                            j_full_charge[i] = (1 - pd.Series(SOC_time[i][int(EndTime_secs.iloc[i][k+1]):int(StartTime_secs.iloc[i][k+2])])).abs().idxmin()
                            time_full_charge[i] = j_full_charge[i] + int(EndTime_secs.iloc[i][k+1])
                            SOC_time[i][time_full_charge[i]:sim_time] = 1
                            
                        SOC_sf[i] = SOC_time[i][int(StartTime_secs.iloc[i][k+2])-1]
                        power_ac_demanded[i][int(EndTime_secs.iloc[i][k+1]):
                            int(StartTime_secs.iloc[i][k+2])] = power_ac.iloc[i]*\
                            self.ChargedAtWork_per*self.VehiclesSubFleet*(1 - 0.01*self.df_VehicleModels['Sitting_cars_per'][self.SubFleetId[i]])                         
                    # Charging at other places    
                    elif Purpose.iloc[i][k+1] == 1.5:
                        t = int(StartTime_secs.iloc[i][k+2]) - int(EndTime_secs.iloc[i][k+1])
                        SOC_time[i][int(EndTime_secs.iloc[i][k+1]):int(StartTime_secs.iloc[i][k+2])] = np.linspace(SOC_sf[i], SOC_sf[i] + self.ChargedAtOther_per*charging_rate*t, t)
                        if any(SOC_time[i][int(EndTime_secs.iloc[i][k+1]):int(StartTime_secs.iloc[i][k+2])] >= 1):
                            j_full_charge[i] = (1 - pd.Series(SOC_time[i][int(EndTime_secs.iloc[i][k+1]):int(StartTime_secs.iloc[i][k+2])])).abs().idxmin()
                            time_full_charge[i] = j_full_charge[i] + int(EndTime_secs.iloc[i][k+1])
                            SOC_time[i][time_full_charge[i]:sim_time] = 1
                            
                        SOC_sf[i] = SOC_time[i][int(StartTime_secs.iloc[i][k+2])-1]
                        power_ac_demanded[i][int(EndTime_secs.iloc[i][k+1]):
                            int(StartTime_secs.iloc[i][k+2])] = power_ac.iloc[i]*\
                            self.ChargedAtOther_per*self.VehiclesSubFleet*(1 - 0.01*self.df_VehicleModels['Sitting_cars_per'][self.SubFleetId[i]])
                                  
                    elif Purpose.iloc[i][k+1] == 1.0:
                        SOC_time[i][int(EndTime_secs.iloc[i][k+1]):int(StartTime_secs.iloc[i][k+2])] = SOC_sf[i]                           
                else:
                    # Again, at home!
                    SOC_time[i][int(EndTime_secs.iloc[i][k]):sim_time] = SOC_sf[i]
                    break
                
        return SOC_time, SOC_sf, power_ac_demanded
 
    def run_baseline_right_away(self, n_days_base, sim_time):
        """ Method to run baseline with charging right away strategy """
        baseline_power = np.zeros([sim_time, ])
        baseline_soc = np.zeros([sim_time, ])   
        baseline_std_soc = np.zeros([sim_time, ]) 
        # Initial SOC of the sub fleets
        SOC = np.ones([self.N_SubFleets,])
        SOC_sf = SOC
        power_ac = self.df_VehicleModels['Max_Charger_AC_Watts'][self.SubFleetId]
        power_dc = np.zeros([self.N_SubFleets,])
        
        for day in range(n_days_base):
            print("Day %i" %(day+1))
            
            v = self.voltage_battery(self.df_VehicleModels['V_SOC_0'][self.SubFleetId],
                                 self.df_VehicleModels['V_SOC_1'][self.SubFleetId],
                                 self.df_VehicleModels['V_SOC_2'][self.SubFleetId], 
                                 self.df_VehicleModels['Number_of_cells'][self.SubFleetId],SOC,0,0)    
            StartTime_secs, EndTime_secs, Miles, Purpose, MilesSubfleet = self.match_schedule(day,SOC,v)                    
            SOC_time, SOC_sf, power_ac_demanded =\
                self.discharge_baseline(StartTime_secs, EndTime_secs, Miles,
                                        Purpose, MilesSubfleet, SOC, SOC_sf,
                                        sim_time, power_ac, v)
                
            # CHARGING STRATEGY   
            time_arrival_home = np.max(EndTime_secs, axis = 1)
            SOC_arrival_home = SOC_sf
            
            for i in range(self.N_SubFleets):
                power_dc[i] = self.power_dc_charger(self.df_VehicleModels['AC_Watts_Losses_0'][self.SubFleetId[i]],
                                                    self.df_VehicleModels['AC_Watts_Losses_1'][self.SubFleetId[i]],
                                                    self.df_VehicleModels['AC_Watts_Losses_2'][self.SubFleetId[i]],
                                                    self.df_VehicleModels['Max_Charger_AC_Watts'][self.SubFleetId[i]],
                                                    power_ac.iloc[i])
            v_oc = self.voltage_battery(self.df_VehicleModels['V_SOC_0'][self.SubFleetId],
                                        self.df_VehicleModels['V_SOC_1'][self.SubFleetId],
                                        self.df_VehicleModels['V_SOC_2'][self.SubFleetId], 
                                        self.df_VehicleModels['Number_of_cells'][self.SubFleetId], SOC_arrival_home, 0, 0)       
            r_batt = self.resistance_battery(self.df_VehicleModels['R_SOC_0'][self.SubFleetId],
                                             self.df_VehicleModels['R_SOC_1'][self.SubFleetId],
                                             self.df_VehicleModels['R_SOC_2'][self.SubFleetId], SOC_arrival_home)            
            i_batt = self.current_charging(v_oc,r_batt,power_dc)
            Ah_rate = i_batt/3600
            charging_rate = Ah_rate/self.df_VehicleModels['Ah_usable'][self.SubFleetId]
            j_full_charge = np.zeros([self.N_SubFleets,], dtype = int)
            time_full_charge = np.zeros([self.N_SubFleets,], dtype = int)
            for i in range(self.N_SubFleets):
                t = sim_time - int(time_arrival_home.iloc[i])
                SOC_time[i][int(time_arrival_home.iloc[i]):sim_time] = np.linspace(SOC_arrival_home[i],SOC_arrival_home[i] + t*charging_rate.iloc[i], t)
                j_full_charge[i] = (1 - pd.Series(SOC_time[i][int(time_arrival_home.iloc[i]):sim_time])).abs().idxmin()
                time_full_charge[i] = j_full_charge[i] + int(time_arrival_home.iloc[i])
                SOC_time[i][time_full_charge[i]:sim_time] = 1
                
                power_ac_demanded[i][int(time_arrival_home.iloc[i]):time_full_charge[i]] = power_ac.iloc[i]*self.VehiclesSubFleet*(1 - 0.01*self.df_VehicleModels['Sitting_cars_per'][self.SubFleetId[i]])
            
            SOC = SOC_time[:,-1]
            SOC_sf = SOC
            
            baseline_power = baseline_power + power_ac_demanded.sum(axis = 0)
            baseline_soc = baseline_soc + SOC_time.mean(axis = 0)
            baseline_std_soc = baseline_std_soc + SOC_time.std(axis = 0)
                    
        return baseline_soc/n_days_base, baseline_power/n_days_base, baseline_std_soc/n_days_base    
 
    def run_baseline_midnight(self, n_days_base, sim_time):
        """ Method to run baseline with midnight charging strategy """
        baseline_power = np.zeros([sim_time, ])
        baseline_soc = np.zeros([sim_time, ])  
        baseline_std_soc = np.zeros([sim_time, ])
        # Initial SOC of the sub fleets
        SOC = np.ones([self.N_SubFleets,])
        SOC_sf = SOC
        power_ac = self.df_VehicleModels['Max_Charger_AC_Watts'][self.SubFleetId]
        power_dc = np.zeros([self.N_SubFleets,])
        
        for day in range(n_days_base):
            print("Day %i" %(day+1))
            
            v = self.voltage_battery(self.df_VehicleModels['V_SOC_0'][self.SubFleetId],
                                 self.df_VehicleModels['V_SOC_1'][self.SubFleetId],
                                 self.df_VehicleModels['V_SOC_2'][self.SubFleetId], 
                                 self.df_VehicleModels['Number_of_cells'][self.SubFleetId],SOC,0,0)    
            StartTime_secs, EndTime_secs, Miles, Purpose, MilesSubfleet = self.match_schedule(day,SOC,v)                    
            SOC_time, SOC_sf, power_ac_demanded =\
                self.discharge_baseline(StartTime_secs, EndTime_secs, Miles,
                                        Purpose, MilesSubfleet, SOC, SOC_sf,
                                        sim_time, power_ac, v)
            
            # CHARGING STRATEGY   
            time_start_charging = 20*3600*pd.Series(np.ones([self.N_SubFleets, ]))
            SOC_arrival_home = SOC_sf
            for i in range(self.N_SubFleets):
                power_dc[i] = self.power_dc_charger(self.df_VehicleModels['AC_Watts_Losses_0'][self.SubFleetId[i]],
                                                     self.df_VehicleModels['AC_Watts_Losses_1'][self.SubFleetId[i]],
                                                     self.df_VehicleModels['AC_Watts_Losses_2'][self.SubFleetId[i]],
                                                     self.df_VehicleModels['Max_Charger_AC_Watts'][self.SubFleetId[i]],
                                                     power_ac.iloc[i])
            v_oc = self.voltage_battery(self.df_VehicleModels['V_SOC_0'][self.SubFleetId],
                                        self.df_VehicleModels['V_SOC_1'][self.SubFleetId],
                                        self.df_VehicleModels['V_SOC_2'][self.SubFleetId], 
                                        self.df_VehicleModels['Number_of_cells'][self.SubFleetId], SOC_arrival_home, 0, 0)       
            r_batt = self.resistance_battery(self.df_VehicleModels['R_SOC_0'][self.SubFleetId],
                                             self.df_VehicleModels['R_SOC_1'][self.SubFleetId],
                                             self.df_VehicleModels['R_SOC_2'][self.SubFleetId], SOC_arrival_home)            
            i_batt = self.current_charging(v_oc,r_batt,power_dc)
            Ah_rate = i_batt/3600
            charging_rate = Ah_rate/self.df_VehicleModels['Ah_usable'][self.SubFleetId]
            j_full_charge = np.zeros([self.N_SubFleets,], dtype = int)
            time_full_charge = np.zeros([self.N_SubFleets,], dtype = int)
            for i in range(self.N_SubFleets):
                t = sim_time - int(time_start_charging.iloc[i])
                SOC_time[i][int(time_start_charging.iloc[i]):sim_time] = np.linspace(SOC_arrival_home[i],SOC_arrival_home[i] + t*charging_rate.iloc[i], t)
                if SOC_time[i][-1] > 1:
                    j_full_charge[i] = (1 - pd.Series(SOC_time[i][int(time_start_charging.iloc[i]):sim_time])).abs().idxmin()
                    time_full_charge[i] = j_full_charge[i] + int(time_start_charging.iloc[i])
                    SOC_time[i][time_full_charge[i]:sim_time] = 1
                
                power_ac_demanded[i][int(time_start_charging.iloc[i]):time_full_charge[i]] =\
                    power_ac.iloc[i]*self.VehiclesSubFleet*(1 - 0.01*self.df_VehicleModels['Sitting_cars_per'][self.SubFleetId[i]])
            
            SOC = SOC_time[:,-1]
            SOC_sf = SOC
            
            baseline_power = baseline_power + power_ac_demanded.sum(axis = 0)
            baseline_soc = baseline_soc + SOC_time.mean(axis = 0)
            baseline_std_soc = baseline_std_soc + SOC_time.std(axis = 0)
                    
        return baseline_soc/n_days_base, baseline_power/n_days_base, baseline_std_soc/n_days_base    

    def run_baseline_tcin(self, n_days_base, sim_time):
        """ Method to run baseline with one hour before the tcin charging strategy """

        baseline_power = np.zeros([sim_time, ])
        baseline_soc = np.zeros([sim_time, ])
        baseline_std_soc = np.zeros([sim_time, ])
        # Initial SOC of the sub fleets
        SOC = np.ones([self.N_SubFleets,])
        SOC_sf = SOC    
        power_ac = self.df_VehicleModels['Max_Charger_AC_Watts'][self.SubFleetId]
        power_dc_arr = np.zeros([self.N_SubFleets, ])
        # One hour before the tcin, the sub fleets must be fully charged        
        hours_before = 1
                    
        v = self.voltage_battery(self.df_VehicleModels['V_SOC_0'][self.SubFleetId],
                                 self.df_VehicleModels['V_SOC_1'][self.SubFleetId],
                                 self.df_VehicleModels['V_SOC_2'][self.SubFleetId], 
                                 self.df_VehicleModels['Number_of_cells'][self.SubFleetId],SOC,0,0)    
        StartTime_secs, EndTime_secs, Miles, Purpose, MilesSubfleet = self.match_schedule(0,SOC,v)
        
        time_charge_morning = np.zeros([self.N_SubFleets,], dtype = int)
        power_ac = self.df_VehicleModels['Max_Charger_AC_Watts'][self.SubFleetId]
        
        for day in range(n_days_base+1):
            if day == 0:
                print("Burn-in day")
            else:
                print("Day %i" %(day))
            
            SOC_time_morning = np.zeros([self.N_SubFleets, sim_time])
            power_ac_demanded = np.zeros([self.N_SubFleets, sim_time])
            
            for i in range(self.N_SubFleets):
                if SOC_sf[i] < 1:
                    power_dc = self.power_dc_charger(self.df_VehicleModels['AC_Watts_Losses_0'][self.SubFleetId[i]],
                                                     self.df_VehicleModels['AC_Watts_Losses_1'][self.SubFleetId[i]],
                                                     self.df_VehicleModels['AC_Watts_Losses_2'][self.SubFleetId[i]],
                                                     self.df_VehicleModels['Max_Charger_AC_Watts'][self.SubFleetId[i]],
                                                     power_ac.iloc[i])
                    v_oc = self.voltage_battery(self.df_VehicleModels['V_SOC_0'][self.SubFleetId[i]],
                                                self.df_VehicleModels['V_SOC_1'][self.SubFleetId[i]],
                                                self.df_VehicleModels['V_SOC_2'][self.SubFleetId[i]], 
                                                self.df_VehicleModels['Number_of_cells'][self.SubFleetId[i]], SOC_sf[i], 0, 0) 
                    r_batt = self.resistance_battery(self.df_VehicleModels['R_SOC_0'][self.SubFleetId[i]],
                                                     self.df_VehicleModels['R_SOC_1'][self.SubFleetId[i]],
                                                     self.df_VehicleModels['R_SOC_2'][self.SubFleetId[i]], SOC_sf[i])
                    i_batt = self.current_charging(v_oc,r_batt,power_dc)
                    Ah_rate = i_batt/3600
                    charging_rate = Ah_rate/self.df_VehicleModels['Ah_usable'][self.SubFleetId[i]]
                    
                    t = int(StartTime_secs.iloc[i][1]) - hours_before*3600 - time_charge_morning[i]
                    if time_charge_morning[i] > 0:
                        SOC_time_morning[i][0:time_charge_morning[i]] = SOC_sf[i]
                        SOC_time_morning[i][time_charge_morning[i]:int(StartTime_secs.iloc[i][1]) - hours_before*3600] = np.linspace(SOC_sf[i], SOC_sf[i] + t*charging_rate,t)
                        
                    else:
                        SOC_time_morning[i][0:int(StartTime_secs.iloc[i][1]) - hours_before*3600] = np.linspace(SOC_sf[i], SOC_sf[i] + t*charging_rate,t)                       
                    
                    SOC_sf[i] = SOC_time_morning[i][int(StartTime_secs.iloc[i][1]) - hours_before*3600-1]
                    SOC_time_morning[i][int(StartTime_secs.iloc[i][1]) - hours_before*3600:int(StartTime_secs.iloc[i][1])] = 1
                    power_ac_demanded[i][time_charge_morning[i]:int(StartTime_secs.iloc[i][1]) - hours_before*3600] = power_ac.iloc[i]*self.VehiclesSubFleet*(1 - 0.01*self.df_VehicleModels['Sitting_cars_per'][self.SubFleetId[i]])

                else:
                    SOC_time_morning[i][0:int(StartTime_secs.iloc[i][1])] = SOC_sf[i]
                    
                SOC_sf[i] = SOC_time_morning[i][int(StartTime_secs.iloc[i][1])-1]
            
            SOC = SOC_sf
            v = self.voltage_battery(self.df_VehicleModels['V_SOC_0'][self.SubFleetId],
                                     self.df_VehicleModels['V_SOC_1'][self.SubFleetId],
                                     self.df_VehicleModels['V_SOC_2'][self.SubFleetId], 
                                     self.df_VehicleModels['Number_of_cells'][self.SubFleetId],SOC_sf,0,0)                      
            SOC_time, SOC_sf, power_ac_demanded_dis =\
                self.discharge_baseline(StartTime_secs, EndTime_secs, Miles,
                                        Purpose, MilesSubfleet, SOC, SOC_sf,
                                        sim_time, power_ac, v) 
                
            for i in range(self.N_SubFleets):    
                SOC_time[i][0:int(StartTime_secs.iloc[i][1])] = SOC_time_morning[i][0:int(StartTime_secs.iloc[i][1])]
            
            power_ac_demanded = power_ac_demanded_dis + power_ac_demanded
            
            # CHARGING STRATEGY   
            time_arrival_home = np.max(EndTime_secs, axis = 1)
            SOC_arrival_home = SOC_sf          
            for i in range(self.N_SubFleets):
                power_dc_arr[i] = self.power_dc_charger(self.df_VehicleModels['AC_Watts_Losses_0'][self.SubFleetId[i]],
                                                 self.df_VehicleModels['AC_Watts_Losses_1'][self.SubFleetId[i]],
                                                 self.df_VehicleModels['AC_Watts_Losses_2'][self.SubFleetId[i]],
                                                 self.df_VehicleModels['Max_Charger_AC_Watts'][self.SubFleetId[i]],
                                                 power_ac.iloc[i])
            v_oc = self.voltage_battery(self.df_VehicleModels['V_SOC_0'][self.SubFleetId],
                                        self.df_VehicleModels['V_SOC_1'][self.SubFleetId],
                                        self.df_VehicleModels['V_SOC_2'][self.SubFleetId], 
                                        self.df_VehicleModels['Number_of_cells'][self.SubFleetId], SOC_arrival_home, 0, 0)       
            r_batt = self.resistance_battery(self.df_VehicleModels['R_SOC_0'][self.SubFleetId],
                                             self.df_VehicleModels['R_SOC_1'][self.SubFleetId],
                                             self.df_VehicleModels['R_SOC_2'][self.SubFleetId], SOC_arrival_home)            
            i_batt = self.current_charging(v_oc,r_batt,power_dc_arr)
            Ah_rate = i_batt/3600
            charging_rate = Ah_rate/self.df_VehicleModels['Ah_usable'][self.SubFleetId]
            # Variation of SOC that must be achieved
            delta_SOC = 1 - SOC_arrival_home
            
            # One hour before the TCIN all the subfleets must be fully charged
            StartTime_secs, EndTime_secs, Miles, Purpose, MilesSubfleet = self.match_schedule(day+1,SOC,v)
            time_full_charge = 24*3600 + StartTime_secs.iloc[:][1] - hours_before*3600
            time_start_charging = np.zeros([self.N_SubFleets,], dtype = int)
            for i in range(self.N_SubFleets):
                time_start_charging[i] = int(time_full_charge.iloc[i] - (delta_SOC[i]/charging_rate.iloc[i]))
                t2 = sim_time - time_start_charging[i]
                if t2 > 0:
                    SOC_time[i][int(time_arrival_home.iloc[i]):time_start_charging[i]] = SOC_arrival_home[i]
                    SOC_time[i][time_start_charging[i]:sim_time] = np.linspace(SOC_arrival_home[i],
                            SOC_arrival_home[i] + t2*charging_rate.iloc[i], t2)
                else:
                    SOC_time[i][int(time_arrival_home.iloc[i]):sim_time] = SOC_arrival_home[i]
                    
                # Power demanded to the grid
                if time_start_charging[i] < 24*3600:
                    power_ac_demanded[i][time_start_charging[i]:sim_time] =\
                        power_ac.iloc[i]*self.VehiclesSubFleet*(1 - 0.01*self.df_VehicleModels['Sitting_cars_per'][self.SubFleetId[i]])
                    time_charge_morning[i] = 0
                else:
                    power_ac_demanded[i][time_start_charging[i]:sim_time] = 0
                    time_charge_morning[i] = int(time_start_charging[i] - 24*3600)
        
            SOC = SOC_time[:,-1]
            SOC_sf = SOC
            
            # Eliminate burn-in day: tcin strategy requires this
            if day != 0:
                baseline_power = baseline_power + power_ac_demanded.sum(axis = 0)
                baseline_soc = baseline_soc + SOC_time.mean(axis = 0)
                baseline_std_soc = baseline_std_soc + SOC_time.std(axis = 0)

        return baseline_soc/(n_days_base), baseline_power/(n_days_base), baseline_std_soc/(n_days_base)
    
    def output_impact_metrics(self, service_name): 
        """
        This function exports the impact metrics of each sub fleet
        """
        impact_metrics_DATA = [["Impact Metrics File"],
                                ["state-of-health", "initial value", "final value", "degradation cost ($)"]]
        for subfleet in range(self.N_SubFleets):
            impact_metrics_DATA.append(["subfleet-"+str(subfleet),
                                        str(self.soh_init[subfleet]),
                                        str(self.soh[subfleet]),
                                        str((self.soh_init[subfleet]-self.soh[subfleet])*self.eol_cost/100)])

        total_cost = sum((self.soh_init-self.soh)*self.eol_cost/100)
        impact_metrics_DATA.append(["Total degradation cost ($):", str(total_cost)])
        impact_metrics_DATA.append(["P_togrid/P_base ratio:", self.ratio_P_togrid_P_base])
        impact_metrics_DATA.append(["Energy Impacts (kWh):", self.energy_impacts])
        
        metrics_dir = join(dirname(dirname(dirname(abspath(__file__)))), 'integration_test', service_name)
        ensure_ddir(metrics_dir)
        metrics_filename = 'ImpactMetrics_' + service_name + '_ElectricVehicles' + '_' + datetime.now().strftime('%Y%m%dT%H%M')  + '.csv'
        with open(join(metrics_dir, metrics_filename), 'w') as csvfile:
            writer = csv.writer(csvfile)
            writer.writerows(impact_metrics_DATA)     
    
    def change_config(self, fleet_config):
        """
        This function updates the fleet configuration settings programatically.
        :param fleet_config: an instance of FleetConfig
        """

        # change config
        self.is_P_priority = fleet_config.is_P_priority
        self.is_autonomous = fleet_config.is_autonomous
        self.FW_Param = fleet_config.FW_Param # FW_Param=[db_UF,db_OF,k_UF,k_OF]
        self.fw_function.db_UF = self.FW_Param[0]
        self.fw_function.db_OF = self.FW_Param[1]
        self.fw_function.k_UF  = self.FW_Param[2]
        self.fw_function.k_OF  = self.FW_Param[3]
        self.autonomous_threshold = fleet_config.autonomous_threshold
        self.Vset = fleet_config.v_thresholds
    
    def assigned_service_kW(self):
        """ 
        This function allows weight to be passed to the service model. 
        Scale the service to the size of the fleet
        """
        return self.service_weight*self.fleet_rating
    
    def print_performance_info(self):
        """
        This function is to dump the performance metrics either to screen or file or both
        :return:
        """
        pass