# -*- coding: utf-8 -*- {{{
#
# Your license here
# }}}

# import Python packages
import sys
from dateutil import parser
from datetime import timedelta
from os.path import dirname, abspath
sys.path.insert(0, dirname(dirname(dirname(abspath(__file__)))))
import numpy as np
import matplotlib.pyplot as plt
# Import modules from "src\services"
from fleet_request import FleetRequest
from fleet_config import FleetConfig

# Use line below if later "battery_inverter_fleet" is moved under the "fleets" folder.
# From fleets.battery_inverter_fleet.battery_inverter_fleet import BatteryInverterFleet

# Currently, "battery_inverter_fleet" is located under "trad_reg_service" for integration testing.
from services.trad_reg_service.battery_inverter_fleet.battery_inverter_fleet import BatteryInverterFleet
from services.trad_reg_service.helpers.historical_signal_helper import HistoricalSignalHelper
from services.trad_reg_service.helpers.clearing_price_helper import ClearingPriceHelper

from services.trad_reg_service.battery_inverter_fleet.grid_info import GridInfo

# TODO: [minor] debate whether to change class and folder names to include dynamic regulation service.
# TODO: [major] for Hung - need to include device fleet type as argument in the future.
# Class for traditional regulation and dynamic regulation services.
class TradRegService():
    """
    This class implements FleetInterface so that it can communicate with a fleet
    """
    _fleet = None

    def __init__(self, *args, **kwargs):
        # fleet's performance and economic value are evaluated for each hour.
        self.sim_time_step = timedelta(hours=1)

        self._historial_signal_helper = HistoricalSignalHelper()
        self._clearing_price_helper = ClearingPriceHelper()

    # The "request_loop" function is the workhorse that manages hourly loops and sending requests & retrieving responses.
    # It returns a 2-level dictionary; 1st level key is the starting time of each hour.
    # TODO: [minor] currently, the start and end times are hardcoded. Ideally, they would be based on promoted user inputs.
    def request_loop(self, service_type = "Traditional",
                     start_time = parser.parse("2017-08-01 16:00:00"),
                     end_time = parser.parse("2017-08-01 21:00:00"),
                     clearing_price_filename = 'historical-ancillary-service-data-2017.xls'):

        # Check service type compatibility.
        if service_type not in ['Traditional', 'Dynamic']:
            raise ValueError("service_type has to be either 'Traditional' or 'Dynamic'!")
        # Generate lists of 2s request and response class objects based on regulation service type (i.e. traditional vs. dynamic).
        request_list_2s_trad, response_list_2s_trad = self.get_signal_lists('Traditional', start_time, end_time)
        if service_type == 'Dynamic':
            request_list_2s_dynm, response_list_2s_dynm = self.get_signal_lists(service_type, start_time, end_time)
            # Assign generic names to signal lists.
            request_list_2s_tot = request_list_2s_dynm
            response_list_2s_tot = response_list_2s_dynm
        else:
            request_list_2s_tot = request_list_2s_trad
            response_list_2s_tot = response_list_2s_trad
        # Returns a Dictionary containing a month-worth of hourly regulation price data indexed by datetime.
        self._clearing_price_helper.read_and_store_clearing_prices(clearing_price_filename, start_time)
        # Create a dictionary to store hourly results incl. performance score, clearing price credit, etc.
        hourly_results = {}
        # Set time duration.
        cur_time = start_time
        one_hour = timedelta(hours=1)

        # Loop through each hour between "start_time" and "end_time".
        while cur_time < end_time - timedelta(minutes=65):
            # Generate 1-hour worth (65 min) of request and response arrays for calculating scores.
            cur_end_time = cur_time + timedelta(minutes=65)
            # Traditional regulation request and response signals are needed regardless of service type.
            request_list_2s_65min_trad = [r.P_req for r in request_list_2s_trad if cur_time <= r.ts_req <= cur_end_time]
            response_list_2s_65min_trad = [r.P_service for r in response_list_2s_trad if cur_time <= r.ts <= cur_end_time]
            request_array_2s_65min_trad = np.asarray(request_list_2s_65min_trad)
            response_array_2s_65min_trad = np.asarray(response_list_2s_65min_trad)
            # For dynamic regulation, mileage ratio calculation is as below.
            if service_type == 'Dynamic':
                # Chop total signals to 1 hour.
                request_list_2s_65min_dynm = [r.P_req for r in request_list_2s_dynm if cur_time <= r.ts_req <= cur_end_time]
                response_list_2s_65min_dynm = [r.P_service for r in response_list_2s_dynm if
                                               cur_time <= r.ts <= cur_end_time]
                request_array_2s_65min_dynm = np.asarray(request_list_2s_65min_dynm)
                response_array_2s_65min_dynm = np.asarray(response_list_2s_65min_dynm)
                # The "mileage ratio" equals "1" for traditional regulation and is > 1 for dynamic regulation.
                Hourly_mileage_trad = self.Hourly_reg_mileage(request_array_2s_65min_trad)
                Hourly_mileage_dynm = self.Hourly_reg_mileage(request_array_2s_65min_dynm)
                mileage_ratio = Hourly_mileage_dynm / Hourly_mileage_trad
                # Assign generic names to signal lists.
                request_list_2s_65min = request_list_2s_65min_dynm
                response_list_2s_65min = response_list_2s_65min_dynm
            else:
                request_list_2s_65min = request_list_2s_65min_trad
                response_list_2s_65min = response_list_2s_65min_trad
                mileage_ratio = 1
            # Convert lists into arrays.
            request_array_2s = np.asarray(request_list_2s_65min)
            response_array_2s = np.asarray(response_list_2s_65min)
            # Slice arrays at 10s intervals - resulted arrays have 390 data points.
            request_array_10s = request_array_2s[::5]
            response_array_10s = response_array_2s[::5]
            # Calculate performance scores for current hour and store in a dictionary keyed by starting time.
            hourly_results[cur_time] = {}
            hourly_results[cur_time]['performance_score'] = self.perf_score(request_array_10s, response_array_10s)
            hourly_results[cur_time]['hourly_integrated_MW'] = self.Hr_int_reg_MW(request_array_2s)
            hourly_results[cur_time]['mileage_ratio'] = mileage_ratio
            hourly_results[cur_time]['Regulation_Market_Clearing_Price(RMCP)'] = self._clearing_price_helper.clearing_prices[cur_time]
            hourly_results[cur_time]['Reg_Clearing_Price_Credit'] = self.Reg_clr_pr_credit(service_type,
                                                                                           hourly_results[cur_time]['Regulation_Market_Clearing_Price(RMCP)'],
                                                                                           hourly_results[cur_time]['performance_score'][0],
                                                                                           hourly_results[cur_time]['hourly_integrated_MW'],
                                                                                           mileage_ratio)
            # Move to the next hour.
            cur_time += one_hour

        # Store request and response parameters in lists for plotting and printing to text files.
        P_request = [r.P_req for r in request_list_2s_tot]
        ts_request = [r.ts_req for r in request_list_2s_tot]
        P_responce = [r.P_service for r in response_list_2s_tot]
        SOC = [r.soc for r in response_list_2s_tot]
        # Plot request and response signals and state of charge (SoC).
        n = len(P_request)
        t = np.asarray(range(n))*(2/3600)
        plt.figure(1)
        plt.subplot(211)
        plt.plot(ts_request, P_request, label='P Request')
        plt.plot(ts_request, P_responce, label='P Responce')
        plt.ylabel('Power (kW)')
        plt.legend(loc='upper right')
        plt.subplot(212)
        plt.plot(ts_request, SOC, label='SoC')
        plt.ylabel('SoC (%)')
        plt.xlabel('Time (hours)')
        plt.legend(loc='lower right')
        plt.show()

        # Store the responses in a text file.
        with open('results.txt', 'w') as the_file:
            for list in zip(ts_request, P_request, P_responce, SOC):
                the_file.write("{},{},{},{}\n".format(list[0],list[1],list[2],list[3]))


        return hourly_results

    # Returns lists of requests and responses at 2s intervals.
    def get_signal_lists(self, service_type, start_time, end_time):
        # Note: If you would like to infer input filename from start_time, use the following
        #       method. However, since the input files are not in the same directory as this code,
        #       file path still needs to be specified.
        #       Thus, revisit this after the codebase becomes production ready, at which time,
        #       you may have the default directory for input files whose path can be passed in
        #       in a different way.

        # Get the name of the Excel file (e.g. "08 2017.xlsx") that contains historical regulation signal data.
        historial_signal_filename = self._historial_signal_helper.get_input_filename(start_time)
        # Returns a DataFrame that contains data in the entire specified sheet (i.e. tab).
        self._historial_signal_helper.read_and_store_historical_signals(historial_signal_filename, service_type)
        # Returns a Dictionary with datetime type keys.
        signals = self._historial_signal_helper.signals_in_range(start_time, end_time)

        sim_step = timedelta(seconds=2)
        requests = []
        responses = []

        # Call the "request" method to get 2s responses in a list, requests are stored in a list as well.
        # TODO: [minor] _fleet.assigned_regulation_MW() is currently only implemented in the fleet model within the same folder but not in the "fleets" folder.
        for timestamp, normalized_signal in signals.items():
            request, response = self.request(timestamp, sim_step, normalized_signal*self._fleet.assigned_regulation_MW())
            requests.append(request)
            responses.append(response)
        #print(requests)
        #print(responses)

        return requests, responses


    # Method for retrieving device fleet's response to each individual request.
    def request(self, ts, sim_step, p, q=0.0): # added input variables; what's the purpose of sim_step??
        fleet_request = FleetRequest(ts=ts, sim_step=sim_step, p=p, q=0.0)
        fleet_response = self.fleet.process_request(fleet_request)
        #print(fleet_response.P_service)
        return fleet_request, fleet_response


    # Score the performance of device fleets for the hour (based on PJM Manual 12).
    # Take 65 min worth of 10s data (should contain 390 data values).
    def perf_score (self, request_array, response_array):
        max_corr_array = []
        max_index_array = []
        prec_score_array = []

        # In each 5-min of the hour, use max correlation to define "delay", "correlation" & "delay" scores.
        # There are twelve (12) 5-min in each hour.
        for i in range(12):
            # Takes 5-min of the input signal data.
            x = request_array[30 * i:30 * (i + 1)]
            #         print('x:', x)
            y = response_array[30 * i:30 * (i + 1)]
            # Refresh the array in each 5-min run.
            corr_score = []
            # If the regulation signal is nearly constant, then correlation score is calculated as:
            # Calculates "1 - absoluate of difference btw slope of request and response signals" (determined by linear regression).
            std_dev_x = np.std(x)
            std_dev_y = np.std(y)
            if std_dev_x < 0.01: # need to vet the threshold later, not specified in PJM manual.
                axis = np.array(np.arange(30.))
                coeff_x = np.polyfit(axis, x, 1) # linear regression when degree = 1.
                coeff_y = np.polyfit(axis, y, 1)
                slope_x = coeff_x[0]
                slope_y = coeff_y[0]
                corr_score_val = max(0, 1 - abs(slope_x - slope_y)) # from PJM manual 12.
                max_index_array = np.append(max_index_array, 0)
                max_corr_array = np.append(max_corr_array, corr_score_val) # "r" cannot be calc'd for constant values in one or both arrays.
            # When request signal varies but response signal is constant, correlation and delay scores will be zero.
            elif std_dev_y < 0.00001:
                corr_score_val = 0
                max_index_array = np.append(max_index_array, 30)
                max_corr_array = np.append(max_corr_array, corr_score_val)
            else:
                # Calculate correlation btw the 5-min input signal and thirty different 5-min response signals,
                # each is delayed at an additional 10s than the previous one; store results.
                # There are thirty (30) 10s in each 5min.
                for j in range(31):
                    y_ = response_array[30 * i + j:30 * (i + 1) + j]
                    #             # for debug use
                    #             print('y:', y)
                    #             x_axis_x = np.arange(x.size)
                    #             plt.plot(x_axis_x, x, "b")
                    #             plt.plot(x_axis_x, y, "r")
                    #             plt.show()
                    # Calculate Pearson Correlation Coefficient btw input and response for the 10s step.
                    corr_r = np.corrcoef(x, y_)[0, 1]
                    # Correlation scores stored in an numpy array.
                    corr_score = np.append(corr_score, corr_r)
                    #         print('corr_score:', corr_score)
                # Locate the 10s moment(step) at which correlation score was maximum among the thirty calculated; store it.
                max_index = np.where(corr_score == max(corr_score))[0][0]
                max_index_array = np.append(max_index_array, max_index)  # array
                # Find the maximum score in the 5-min; store it.
                max_corr_array = np.append(max_corr_array, corr_score[max_index])  # this is the correlation score array
            # Calculate the coincident delay score associated with max correlation in each 5min period.
            delay_score = np.absolute((10 * max_index_array - 5 * 60) / (5 * 60))  # array
            # Calculate error at 10s intervals and store in an array.
            error = np.absolute(y - x) / (np.absolute(x).mean())
            # Calculate 5-min average Precision Score as the average error.
            prec_score = max(0, 1 - 1 / 30 * error.sum())
            prec_score_array = np.append(prec_score_array, prec_score)

        # # for debug use
        # print('delay_score:', delay_score)
        # print('max_index_array:', max_index_array)
        # print('max_corr_array:', max_corr_array)
        # print('prec_score_array:', prec_score_array)

        # Calculate average "delay", "correlation" and "precision" scores for the hour.
        Delay_score = delay_score.mean()
        Corr_score = max_corr_array.mean()
        Prec_score = prec_score_array.mean()

        #     # for debug use
        #     x_axis_error = np.arange(error.size)
        #     plt.scatter(x_axis_error, error)
        #     plt.show()

        # Calculate the hourly overall Performance Score.
        Perf_score = (Delay_score + Corr_score + Prec_score)/3

        #     # for debug use
        # # Plotting and Printing results
        # x_axis_sig = np.arange(request_array[0:360].size)
        # x_axis_score = np.arange(max_corr_array.size)
        #
        # plt.figure(1)
        # plt.subplot(211)
        # plt.plot(x_axis_sig, request_array[0:360], "b")
        # plt.plot(x_axis_sig, response_array[0:360], "r")
        # plt.legend(('RegA signal', 'CReg response'), loc='lower right')
        # plt.show()
        #
        # plt.figure(2)
        # plt.subplot(212)
        # plt.plot(x_axis_score, max_corr_array, "g")
        # plt.plot(x_axis_score, delay_score, "m")
        # plt.legend(('Correlation score', 'Delay score'), loc='lower right')
        # plt.show()
        #
        # print('Delay_score:', Delay_score)
        # print('Corr_score:', Corr_score)
        # print('Prec_score:', Prec_score)
        # print('Perf_score:', Perf_score)

        return (Perf_score, Delay_score, Corr_score, Prec_score)


    # Based on PJM Manual 28 (need to verify definition, not found in manual).
    def Hr_int_reg_MW (self, input_sig):
        # Take one hour of 2s RegA data
        Hourly_Int_Reg_MW = np.absolute(input_sig).sum() * 2 / 3600
        # print(Hourly_Int_Reg_MW)
        return Hourly_Int_Reg_MW



    # Calculate an hourly value of "Regulation Market Clearing Price Credit" for the regulation service provided.
    # Based on PJM Manual 28.
    def Reg_clr_pr_credit(self, service_type, RM_pr, pf_score, reg_MW, mi_ratio):
        # Arguments:
        # service_type - traditional or dynamic.
        # RM_pr - RMCP price components for the hour.
        # pf_score - performance score for the hour.
        # reg_MW - "Hourly-integrated Regulation MW" for the hour.
        # mi_ratio - mileage ratio for the hour.

        # Prepare key parameters for calculation.
        RMCCP = RM_pr[1]
        RMPCP = RM_pr[2]

        print("Hr_int_reg_MW:", reg_MW)
        print("Pf_score:", pf_score)
        print("RMCCP:", RMCCP)
        print("RMPCP:", RMPCP)

        # Calculate "Regulation Market Clearing Price Credit" and two components.
        # Minimum perf score is 0.25, otherwise forfeit regulation credit (and lost opportunity) for the hour (m11 3.2.10).
        if pf_score < 0.25:
            Reg_RMCCP_Credit = 0
            Reg_RMPCP_Credit = 0
        else:
            Reg_RMCCP_Credit = reg_MW * pf_score * RMCCP
            Reg_RMPCP_Credit = reg_MW * pf_score * mi_ratio * RMPCP
        Reg_Clr_Pr_Credit = Reg_RMCCP_Credit + Reg_RMPCP_Credit

        # # for debug use
        # print("Reg_Clr_Pr_Credit:", Reg_Clr_Pr_Credit)
        # print("Reg_RMCCP_Credit:", Reg_RMCCP_Credit)
        # print("Reg_RMPCP_Credit:", Reg_RMPCP_Credit)

        # "Lost opportunity cost credit" (for energy sources providing regulation) is not considered,
        # because it does not represent economic value of the provided service.

        return (Reg_Clr_Pr_Credit, Reg_RMCCP_Credit, Reg_RMPCP_Credit)



    # Calculate the device fleet's "mileage" for the hour.
    # Based on PJM Manual 11.
    def Hourly_reg_mileage(self, input_sig):
        # Take one hour of regulation signal data.
        mileage_array = input_sig[1:1800] - input_sig[0:1799]
        #     Reg_signal_array = input_sig[1:1800]
        #     print(mileage_array)
        #     x_axis = np.arange(mileage_array.size)
        #     plt.plot(x_axis, Reg_signal_array,"b")
        #     plt.plot(x_axis, mileage_array,"r")
        #     plt.show()
        Mileage = np.absolute(mileage_array).sum()

        return Mileage



    def change_config(self):
        fleet_config = FleetConfig(is_P_priority=True, is_autonomous=False, autonomous_threshold=0.1)
        self._fleet.change_config(fleet_config)


    # Use "dependency injection" to allow method "fleet" be used as an attribute.
    @property
    def fleet(self):
        return self._fleet

    @fleet.setter
    def fleet(self, value):
        self._fleet = value


# Run from this file.
if __name__ == '__main__':
    service = TradRegService()

    #fleet = BatteryInverterFleet('C:\\Users\\jingjingliu\\gmlc-1-4-2\\battery_interface\\src\\fleets\\battery_inverter_fleet\\config_CRM.ini')
    # TODO: [minor] I don't understand why this line of code works. I can't find function "Gridinfo".
    grid = GridInfo('battery_inverter_fleet/Grid_Info_DATA_2.csv')
    battery_inverter_fleet = BatteryInverterFleet(GridInfo=grid)  # establish the battery inverter fleet with a grid.
    service.fleet = battery_inverter_fleet

    # Test request_loop()
    # Use line below for testing TRADITIONAL regulation service.
    # fleet_response = service.request_loop(service_type = "Traditional",
    #                                       start_time = parser.parse("2017-08-01 16:00:00"), end_time = parser.parse("2017-08-01 21:00:00"),
    #                                       clearing_price_filename = 'historical-ancillary-service-data-2017.xls')
    # Use line below for testing DYNAMIC regulation service.
    fleet_response = service.request_loop(service_type = "Dynamic",
                                          start_time = parser.parse("2017-08-01 16:00:00"), end_time = parser.parse("2017-08-02 15:00:00"),
                                          clearing_price_filename = 'historical-ancillary-service-data-2017.xls')

    # Print results in the 2-level dictionary.
    for key_1, value_1 in fleet_response.items():
        print(key_1)
        for key_2, value_2 in value_1.items():
            print('\t\t\t\t\t\t', key_2, value_2)


#cd C:\Users\jingjingliu\gmlc-1-4-2\battery_interface\src\services\trad_reg_service\
#python trad_reg_service.py
