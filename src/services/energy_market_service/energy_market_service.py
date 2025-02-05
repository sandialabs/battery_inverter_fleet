# -*- coding: utf-8 -*- {{{
#
# Your license here
# }}}

import sys
from dateutil import parser
from datetime import datetime, timedelta
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

from os.path import dirname, abspath, join
sys.path.insert(0,dirname(dirname(dirname(abspath(__file__)))))

from utils import ensure_ddir
from fleet_request import FleetRequest


class EnergyMarketService(object):
    
    # Private attribute that represents the fleet
    _fleet = None
        
    def __init__(self, *args, **kwargs):
        # Set current directory as base_path
        self.base_path = dirname(abspath(__file__))
        self.requests = self.create_base_request()
            
    def create_base_request(self,
                            ts = datetime(2017, 1, 1, 00, 0, 00, 000000),
                            hrs = 24,
                            sim_step = timedelta(hours = 1)):
        """
        Method to create a list of requests with P_req = None to call the forecast method
        of the fleet and obtain the API variables that are used
        by the energy market service class
        """
        requests = []
        for i in range(hrs):
            req = FleetRequest(ts+i*sim_step, sim_step, ts, None, 0.)
            requests.append(req)        
        return requests
                     
    def get_forecast_api_variables(self):
        """
        Method to run the forecast method of the fleet and return the API variables
        that the energy market service needs to run its dispatch algorithm
        """
        print('Running fleet forecast for the %s ...' %self._fleet.__class__.__name__)
        forecast_base = self._fleet.forecast(self.requests)
        print('--Done--')
        
        hrs = len(forecast_base)      
        e_in = np.array([forecast_base[i].Eff_charge for i in range(hrs)])
        e_out = np.array([forecast_base[i].Eff_discharge for i in range(hrs)])   
        p_service_max = np.array([forecast_base[i].P_service_max for i in range(hrs)])   
        p_service_min = np.array([forecast_base[i].P_service_min for i in range(hrs)])  
        p_service = np.array([forecast_base[i].P_service for i in range(hrs)])
        strike_price = np.array([forecast_base[i].Strike_price for i in range(hrs)])

        rt = np.multiply.outer(e_in*0.01, e_out*0.01)*100
        np.fill_diagonal(rt, 0)
        
        strike_price = (strike_price*np.ones([hrs,hrs])).T
        print(strike_price)
 
        return (rt, p_service_max, p_service_min, p_service, strike_price)
    
    def dispatch_algorithm(self):
        """ 
        Method where the dispatch algorithm is implemented. This method should:
            1. Call self.get_forecast_api_values to get API variables: roundtrip_eff, energy, strike price, ...
            2. Run the dispatch algorithm to generate P_opt (optimal power profile)
            3. Return P_req = P_opt
        """
        # Needed API variables: roundtrip efficiency, p_services, strike prices
        rt, p_service_max, p_service_min, p_service, strike = self.get_forecast_api_variables()

        #Constants
        INF = 999999
        timesteps = 24
        nChg = 2  #Number of timesteps required to charge or discharge (< timesteps/2)
        tFull = 500 #tFull=tRestore, Time when system must have full charge 
        
        # Read prices
        self.price = np.genfromtxt(join(self.base_path, 'CAISOApr2016Hourly.csv'), delimiter=',')

        """
        Read round trip eff and strike for pairs of charge & discharge hours
        eff and strike are square matrices of dimensions [timesteps, timesteps]
        elements on diagonal and above are for charge in timestep i and discharge in j
        elements below the diagonal are for dicharge in timestep i and charge in j
        """
        eff = rt
        
        #Read charge state - for this implementation just use state at period 0
        charged = np.genfromtxt(join(self.base_path, 'ChargeStateOffHourly.csv'), delimiter=',')
        
        # Construct profit table: profit = -price(charge) + eff(i,j)*price(discharge)
        # Fill profit matrix with NaNs
        profit = np.full([timesteps, timesteps], np.nan)
        """
        Profit depends upon order of charge and discharge 
        if charge period i < discharge period j it must be discharged at midnight 
        if charge period i > discharge period j it must be charged at midnight
        """      
        for i in range(timesteps):
            for j in range(timesteps):
                profit[i,j] = -self.price[i] + eff[i,j]*self.price[j]
                #print(i, j, profit[i,j], price[i], eff[i,j])
        
        # Construct value table: value = profit - strike(i,j)
        value = np.full([timesteps, timesteps], np.nan)
        for i in range(timesteps):
            for j in range(timesteps):
                value[i,j] = profit[i,j] - strike[i,j]
                #print(i, j, profit[i,j], strike[i,j], value[i,j])
        
        def plotCurve(curve, title, xLabel, yLabel): 
            hour = range(timesteps)
            plt.figure()
            plt.plot(hour, curve, label = title)
            plt.legend()
            plt.xlabel(xLabel)
            plt.ylabel(yLabel)
            plt.grid(b=True, which='both')
            plt.show()
        
        def plotHeatMap(matrix, xLabel, yLabel, scaleLabel):
            import matplotlib.cm as cm
            #cmap = cm.get_cmap('nipy_spectral_r')
            #cmap = cm.get_cmap('plasma_r')
            plt.figure()
            cmap = cm.get_cmap('RdYlGn')
            nx,ny = np.shape(matrix)
            cs = plt.pcolor(matrix, cmap=cmap)
            cb = plt.colorbar(cs,orientation = 'vertical')
            cb.set_label(scaleLabel)
            plt.xlim(0,nx)
            plt.ylim(0,ny)
            plt.xlabel(xLabel)
            plt.ylabel(yLabel)
            plt.grid(True)
            plt.show()
            return
        
        def oneCycleNPer(INF, nChg, value, startT, stopT, tFull):
        # One daily cycle with nChg period contiguous charge and discharge times
        # Array indexs first period of chorge or discharge event
            nDim = stopT - startT
            print('nDim = ', nDim)
            #Dimension matrices and fill with NANs
            nProfit = np.full([nDim, nDim], np.nan)
            nValue = np.full([nDim, nDim], np.nan)
            # Compute profit array for charge period and discharge period lagged by nChg
            # or more time periods
            
            if charged[startT] == 0:     # Discharged at start of period 
                for i in range(nDim - 2*nChg + 2):
                    for j in range (i + nChg, nDim - nChg + 2):
                        nProfit[i, j] = profit[startT + i, startT + j]
                        nValue[i, j] = value[startT + i, startT + j]
                        for k in range(1, nChg): 
                            nProfit[i, j] = nProfit[i , j] + profit[startT + i + k, startT + j + k] 
                            nValue[i, j] = nValue[i, j] + value[startT + i + k, startT + j + k]
                        #Test to see if charge too late, after time tFull
                        if i > (tFull - nChg):
                            nValue[i,j] = - INF
                        #Test to see if charged then discharged before time tFull
                        if j > tFull - nChg:
                            nValue[i,j] = - INF
                # Find charge-discharge hours with maximum value for single cycle
                maxValue = -INF
                for i in range(nDim):
                    for j in range(i + nChg, nDim - nChg + 1):
                        if nValue[i,j] > maxValue:
                            maxValue = nValue[i,j]
                            chargeMax = i
                            dischargeMax = j
                charged[stopT] = 0
            else:   # Charged at start of period (just change i and j indices in loops)
                for j in range(nDim - 2*nChg + 2):
                    for i in range (j + nChg, nDim - nChg + 2):
                        nProfit[i, j] = profit[startT + i, startT + j]
                        nValue[i, j] = value[startT + i, startT + j]
                        for k in range(1, nChg): 
                            nProfit[i, j] = nProfit[i , j] + profit[startT + i + k, startT + j + k] 
                            nValue[i, j] = nValue[i, j] + value[startT + i + k, startT + j + k]
                        #Test to see if discharged before time tFull and charged after time tFull
                        if j > tFull:
                            if i > (tFull - nChg):
                                nValue[i,j] = - INF
                # Find charge-discharge hours with maximum value for single cycle
                maxValue = -INF
                for j in range(nDim):
                    for i in range(j + nChg, nDim - nChg + 1):
                        if nValue[i,j] > maxValue:
                            maxValue = nValue[i,j]
                            chargeMax = i
                            dischargeMax = j
                charged[stopT] = 1
            return(chargeMax + startT, dischargeMax + startT, maxValue, charged[stopT])
            
        plotCurve(self.price, 'CAISO Price Mar 2016', 'time', '$/MWh')
        plotHeatMap(eff, 'Discharge time', 'Charge time', 'Round Trip efficiency (%)')
        plotHeatMap(strike, 'Discharge time', 'Charge time', 'Strike price-elasticity ($/MWh)')
        plotHeatMap(profit, 'Discharge time', 'Charge time', 'Energy arbitrage profit ($/MWh)')
        plotHeatMap(value, 'Discharge time', 'Charge time', 'Value = Profit - Strike price ($/MWh)')
        
        #Call oneCycleNPer for single daily cycle
        startT = 0
        stopT = timesteps - 1
        chargeMax, dischargeMax, maxValue, charged[stopT] = oneCycleNPer(INF, nChg, value, startT, stopT, tFull)
        p_tcharge = abs(p_service_max[chargeMax]) - abs(p_service_min[chargeMax])
        p_tdischarge = abs(p_service_max[dischargeMax]) - abs(p_service_min[dischargeMax])
        Preq = min(p_tcharge, p_tdischarge) #request dispatch power
        print('startT = ', startT, 'stopT = ', stopT)
        print('Charge state at beginning of period = ', charged[startT] )
        print('Charge state at end of period = ', charged[stopT] )
        print('Solution for single daily cycle ', nChg, 'timesteps to charge')
        print('Max value = ', maxValue, '$/MWh')
        print('Charge time = ', chargeMax)
        print('Discharge time = ', dischargeMax)
        print('Dispatch Power Request = ', Preq)
        print()
        
        # Write dispatch orders for single daily cycle to file 
        dispatch = open(join(self.base_path, 'dispatchOrders.csv'), 'a')
        header = ['Single cycle output:, timesteps, startT, stopT, charged[startT], nChg, tFull, maxValue, chargeMax, dischargeMax \n']
        dispatch.writelines( header )
        data = [str(timesteps), '\n', str(startT), '\n', str(stopT), '\n', str(charged[startT]), '\n', 
                str(nChg), '\n', str(tFull), '\n', str(maxValue), '\n', str(chargeMax), '\n', str(dischargeMax), '\n']
        dispatch.writelines( data )
        
        #Call oneCycleNPer twice for the day
        #Call oneCycleNPer for first cycle
        startT = 0
        stopT = int(timesteps/2) - 1
        p_tcharge = abs(p_service_max[chargeMax]) - abs(p_service_min[chargeMax])
        p_tdischarge = abs(p_service_max[dischargeMax]) - abs(p_service_min[dischargeMax])
        Preq = min(p_tcharge, p_tdischarge) #request dispatch power
        chargeMax, dischargeMax, maxValue, charged[stopT] = oneCycleNPer(INF, nChg, value, startT, stopT, tFull)
        print('startT = ', startT, 'stopT = ', stopT)
        print('Charge state at beginning of period = ', charged[startT] )
        print('Charge state at end of period = ', charged[stopT] )
        print('Solution for single cycle ', nChg, 'timesteps to charge')
        print('Max value = ', maxValue, '$/MWh')
        print('Charge time = ', chargeMax)
        print('Discharge time = ', dischargeMax)
        print('Dispatch Power Request = ', Preq)
        print()
        
        # Write dispatch orders for first cycle to file 
        dispatch = open(join(self.base_path, 'dispatchOrders.csv'), 'a')
        header = ['First cycle output:, timesteps, startT, stopT, charged[startT], nChg, tFull, maxValue, chargeMax, dischargeMax \n']
        dispatch.writelines( header )
        data = [str(timesteps), '\n', str(startT), '\n', str(stopT), '\n', str(charged[startT]), '\n', 
                str(nChg), '\n', str(tFull), '\n', str(maxValue), '\n', str(chargeMax), '\n', str(dischargeMax), '\n']
        dispatch.writelines( data )
        
        #Call oneCycleNPer for second cycle
        startT = int(timesteps/2)
        #Charge state at beginning of period = charge state from previous period
        charged[startT] = charged[stopT]
        stopT = timesteps - 1
        p_tcharge = abs(p_service_max[chargeMax]) - abs(p_service_min[chargeMax])
        p_tdischarge = abs(p_service_max[dischargeMax]) - abs(p_service_min[dischargeMax])
        Preq = min(p_tcharge, p_tdischarge) #request dispatch power
        chargeMax, dischargeMax, maxValue, charged[stopT] = oneCycleNPer(INF, nChg, value, startT, stopT, tFull)
        print('startT = ', startT, 'stopT = ', stopT)
        print('Charge state at beginning of period = ', charged[startT] )
        print('Charge state at end of period = ', charged[stopT] )
        print('Solution for single cycle ', nChg, 'timesteps to charge')
        print('Max value = ', maxValue, '$/MWh')
        print('Charge time = ', chargeMax)
        print('Discharge time = ', dischargeMax)
        print('Dispatch Power Request = ', Preq)
        print()
        
        # Write dispatch orders for second cycle to file 
        dispatch = open(join(self.base_path, 'dispatchOrders.csv'), 'a')
        header = ['Second cycle output:, timesteps, startT, stopT, charged[startT], nChg, tFull, maxValue, chargeMax, dischargeMax \n']
        dispatch.writelines( header )
        data = [str(timesteps), '\n', str(startT), '\n', str(stopT), '\n', str(charged[startT]), '\n', 
            str(nChg), '\n', str(tFull), '\n', str(maxValue), '\n', str(chargeMax), '\n', str(dischargeMax), '\n']
        dispatch.writelines( data )
        dispatch.close()
    
        # Return charge time (t1), discharge time (t2), and the request in kW
        return chargeMax, dischargeMax, Preq  
    
    def request_loop(self, start_time = parser.parse("2016-04-01 00:00:00"),
                     sim_step = timedelta(minutes=5),
                     end_time = parser.parse("2016-04-01 23:59:59")):
        """
        Method to run the request generated from the dispatch algorithm to see
        how in practice this is tracked
        """
        fleet_name = self._fleet.__class__.__name__
    
        # Return results from dispatch algorithm
        t_charge, t_discharge, p_req = self.dispatch_algorithm()
        
        ndx_end = 24
        #sim_step = timedelta(minutes=5)
        sim_time = int(ndx_end*3600/sim_step.seconds)
        requests = []
        responses = []
        
        # Start charging, end charging, start discharging, end discharging
        charge_strt = int(t_charge*(3660/sim_step.seconds))
        charge_end = int((t_charge+1)*(3660/sim_step.seconds))
        disch_strt = int(t_discharge*(3660/sim_step.seconds))
        disch_end = int((t_discharge+1)*(3660/sim_step.seconds))
        
        # Build the process request for the 24 hours cycle
        p_request = np.zeros([sim_time, ])
        p_request[charge_strt:charge_end] = -p_req
        p_request[disch_strt:disch_end] = p_req

        ts = start_time
        for k in range(sim_time):     
            request, response = self.request(ts, sim_step, start_time, p_request[k])
            requests.append(request)
            responses.append(response)  
            ts += sim_step
            print('Processing dispatch request at time ts = %s' %ts)
            
        request_list_1h = []
        for r in requests:
            if r.P_req is not None:
                request_list_1h.append((r.ts_req, r.P_req / 1000))
            else:
                request_list_1h.append((r.ts_req, r.P_req))
        request_df_1h = pd.DataFrame(request_list_1h, columns=['Date_Time', 'Request'])
        
        if 'battery' in fleet_name.lower():
            # Include battery SoC in response list for plotting purposes
            response_list_1h = [(r.ts, r.P_service / 1000, r.P_togrid, r.P_base, r.soc) for r in responses]
            response_df_1h = pd.DataFrame(response_list_1h, columns=['Date_Time', 'Response', 'P_togrid', 'P_base', 'SoC'])
        else:
            
            response_list_1h = [(r.ts, np.nan if r.P_service is None else r.P_service / 1000, r.P_togrid, r.P_base) for r in responses]
            response_df_1h = pd.DataFrame(response_list_1h, columns=['Date_Time', 'Response', 'P_togrid','P_base'])

        # This merges/aligns the requests and responses dataframes based on their time stamp 
        # into a single dataframe
        df_1h = pd.merge(
            left=request_df_1h,
            right=response_df_1h,
            how='left',
            left_on='Date_Time',
            right_on='Date_Time')

        df_1h['P_togrid'] = df_1h['P_togrid'] / 1000
        df_1h['P_base'] = df_1h['P_base'] / 1000

        # Plot entire analysis period results and save plot to file
        # We want the plot to cover the entire df_1h dataframe
        plot_dir = join(dirname(dirname(dirname(abspath(__file__)))), 'integration_test', 'energy_market_service')
        ensure_ddir(plot_dir)
        plot_filename = 'SimResults_EnergyMarket_' + fleet_name + '_' + datetime.now().strftime('%Y%m%dT%H%M')  + '.png'
        plt.figure(1)
        plt.figure(figsize=(15, 8))
        ax1 = plt.subplot(311)
        if not(all(pd.isnull(df_1h['Request']))):
            l1, = ax1.plot(df_1h.Date_Time, df_1h.Request,
                           label='P_Request', linestyle = '-')
        if not(all(pd.isnull(df_1h['Response']))):
            l2, = ax1.plot(df_1h.Date_Time, df_1h.Response,
                           label='P_Response', linestyle = '--')
        ax1.set_ylabel('Power (MW)')
        ax2 = ax1.twinx()
        l3, = ax2.plot(pd.date_range(start_time, periods=24, freq = 'H').tolist(), self.price,
                       label = 'Price ($/MWh)', linestyle = '-.', color = 'red')
        ax2.set_ylabel('Price ($/MWh)', color='r')
        ax2.tick_params('y', colors='r')
        plt.legend(handles=[l1, l2, l3])
            
        plt.subplot(312)
        if not(all(pd.isnull(df_1h['P_base']))):
            plt.plot(df_1h.Date_Time, df_1h.P_base + df_1h.Request, label='P_base + P_Request', linestyle = '-')       
        if not(all(pd.isnull(df_1h['P_togrid']))):
            plt.plot(df_1h.Date_Time, df_1h.P_togrid, label='P_togrid', linestyle = '--')
        if not(all(pd.isnull(df_1h['P_base']))):
            plt.plot(df_1h.Date_Time, df_1h.P_base, label='P_base', linestyle = '-.')
        plt.ylabel('Power (MW)')
        plt.legend()
        if 'battery' is not fleet_name.lower():
            plt.xlabel('Time')
        
        if 'battery' in fleet_name.lower():
            if not(all(pd.isnull(df_1h['SoC']))):
                plt.subplot(313)
                plt.plot(df_1h.Date_Time, df_1h.SoC, label='SoC', linestyle = '-')
                plt.ylabel('SoC (%)')
                plt.xlabel('Time')
        plt.savefig(join(plot_dir, plot_filename), bbox_inches='tight')
        plt.close()
    
        return requests, responses
  
    def request(self, ts, sim_step, start_time, p, q=0.0):
        fleet_request = FleetRequest(ts=ts, sim_step=sim_step,
                                     start_time=start_time, p=p, q=0.0)
        fleet_response = self.fleet.process_request(fleet_request)
        return fleet_request, fleet_response
        
    @property
    def fleet(self):
        return self._fleet

    @fleet.setter
    def fleet(self, value):
        self._fleet = value
    

def main():
    from grid_info import GridInfo
    
    ts = datetime(2018, 9, 20, 00, 0, 00, 000000)
    grid = GridInfo('Grid_Info_DATA_2.csv')   
    
    # fleets = ['BatteryInverter', 'ElectricVehicle', 'PV', 'WaterHeater', 'Electrolyzer', 'FuelCell', 'HVAC', 'Refridge' ]
    fleets = ['ElectricVehicle']
    
    energy_market = EnergyMarketService()
    
    for fleet in fleets:
        if fleet == 'ElectricVehicle':
            from fleets.electric_vehicles_fleet.electric_vehicles_fleet import ElectricVehiclesFleet
            fleet = ElectricVehiclesFleet(grid, ts)
            energy_market.fleet = fleet   

    req, resp = energy_market.request_loop()
    return req, resp


if __name__ == "__main__":
   req, resp = main()
