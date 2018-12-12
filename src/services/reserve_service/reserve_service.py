# -*- coding: utf-8 -*- {{{
#
# Your license here
# }}}

# Import Python packages
import sys
from dateutil import parser
from datetime import datetime, timedelta
from os.path import dirname, abspath
sys.path.insert(0, dirname(dirname(dirname(abspath(__file__)))))
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
# Import modules from "src\services"
from fleet_request import FleetRequest
from fleet_config import FleetConfig

from pdb import set_trace as bp


from services.reserve_service.helpers.historical_signal_helper import HistoricalSignalHelper
from services.reserve_service.helpers.clearing_price_helper import ClearingPriceHelper



# Class for synchronized reserve service.
class ReserveService():
    """
    This class implements FleetInterface so that it can communicate with a fleet
    """
    _fleet = None

    def __init__(self, *args, **kwargs):
        self._historial_signal_helper = HistoricalSignalHelper()
        self._clearing_price_helper = ClearingPriceHelper()

    # The "request_loop" function is the workhorse that manages high-level monthly loops and sending requests & retrieving responses.
    # The time step for simulating fleet's response is at 1 minute.
    # It returns a 2-level dictionary; 1st level key is the month.
    # TODO: [minor] currently, the start and end times are hardcoded. Ideally, they would be based on promoted user inputs.
    def request_loop(self, start_time=parser.parse("2017-01-01 00:00:00"),
                     end_time=parser.parse("2017-01-01 05:00:00"),
                     clearing_price_filename="201701.csv"):

        # Generate lists of 1-min request and response class objects.
        request_list_1m_tot, response_list_1m_tot = self.get_signal_lists(start_time, end_time)
        # Returns a Dictionary containing a month-worth of hourly SRMCP price data indexed by datetime.
        self._clearing_price_helper.read_and_store_clearing_prices(clearing_price_filename, start_time)

        # Generate lists containing tuples of (timestamp, power) for request and response
        request_list_1m = [(r.ts_req, r.P_req) for r in request_list_1m_tot]
        # Include battery SoC in response list for plotting purposes
        response_list_1m = [(r.ts, r.P_service, r.soc) for r in response_list_1m_tot]
        # Convert the lists of tuples into dataframes
        request_df_1m = pd.DataFrame(request_list_1m, columns=['Date_Time', 'Request'])
        response_df_1m = pd.DataFrame(response_list_1m, columns=['Date_Time', 'Response', 'SoC'])
        # This merges/aligns the requests and responses dataframes based on their time stamp 
        # into a single dataframe
        df_1m = pd.merge(
            left=request_df_1m,
            right=response_df_1m,
            how='left',
            left_on='Date_Time',
            right_on='Date_Time')

        # Plot entire analysis period results and save plot to file
        # We want the plot to cover the entire df_1m dataframe
        plot_dir = dirname(abspath(__file__)) + '\\plots\\'
        plot_filename = datetime.now().strftime('%Y%m%d') + '_all_events.png'
        plt.figure(1)
        plt.subplot(211)
        plt.plot(df_1m.Date_Time, df_1m.Request, label='P Request')
        plt.plot(df_1m.Date_Time, df_1m.Response, label='P Response')
        plt.ylabel('Power (kW)')
        plt.legend(loc='best')
        plt.subplot(212)
        plt.plot(df_1m.Date_Time, df_1m.SoC, label='SoC')
        plt.ylabel('SoC (%)')
        plt.xlabel('Time')
        plt.savefig(plot_dir + plot_filename, bbox_inches='tight')
        plt.close()

        # Ensure that at least one event occurs within the specified time frame
        if df_1m.Request.sum() == 0:
            return(print('There are no events in the time frame you specified.'))

        # We can then do the following to break out the indices corresponding to events:
        # 1) np.where will return the dataframe indices where the request value is greater than 0
        # 2) np.split will split the array of indices from (1) into multiple arrays, each corresponding
        #    to a single event.  Here, we split the array from (1) based on where the difference between
        #    indices is greater than 1 (we assume that continuous indices correspond to the same event).
        event_indices = np.where(df_1m.Request > 0.)[0]
        event_indices_split = np.split(event_indices, np.where(np.insert(np.diff(event_indices), 0, 1) > 1)[0])

        # Set previous event end to be 20170101, since nothing comes before the first event
        # (This is for calculating the shortfall of the first event, if applicable)
        previous_event_end = pd.Timestamp('01/01/2017 00:00:00')

        # Create empty data frame to store results in
        results_df = pd.DataFrame(columns=['Time_Start', 'Time_End', 'Duration_mins',
            'Delta_Previous_Event_mins', 'SRMCP_$/MW', 'Response_Max_MW',
            'Response_Max_Time_mins', 'Response_Committed_Time_mins',
            'Response_Start_MW', 'Response_End_MW', 'Response_First10Min_MW',
            'Response_After11Min_MW', 'Response_After11Min_Ratio',
            'Request_MW', 'Shortfall_MW', 'Value_$'])

        # Then, we can take everything event-by-event.  "event_indices" contains the list of 
        # df_1m indices corresponding to a single event.
        for event_indices in event_indices_split:

            time_stamps_per_minute = 1 # each time stamp corresponds to a minute

            # Check if event is at least 11 minutes; if shorter, we'll need to add indices for
            # an extra minute at the end of the event
            shorter_than_11_min = ((df_1m.Date_Time[event_indices[len(event_indices) - 1]] - df_1m.Date_Time[event_indices[0]]).seconds / 60.) < 11.

            # Create list of indices to add to start of event_indices representing the minute prior to the event starting
            # The np.arange call here creates a descending list of numbers, starting from the first index in event_indices
            # These numbers correspond to the extra indices we need to include for the -1 minute
            event_indices_prior_minute = [event_indices[0] - x for x in np.arange(time_stamps_per_minute, 0, -1)] 
            # Add the indices for the event prior to the event starting to the start of the event_indices list
            # np.insert will insert numbers into an array at the point you specify:
            # here, we want the number(s) to go at the start, signified by [0]*len(event_indices_prior_minute)
            event_indices_ready = np.insert(
                event_indices,
                [0] * len(event_indices_prior_minute),
                event_indices_prior_minute)
            # If the event is shorter than 11 minutes, we want to account for an extra minute at the end
            if shorter_than_11_min:
                # Now generate a list of indices to add to the end of event_indices_ready representing an extra minute
                event_indices_after_minute = [event_indices[len(event_indices) - 1] + x for x in np.arange(1, time_stamps_per_minute + 1)]
                # Append that extra minute's worth of indices to the end of event_indices_ready
                event_indices_ready = np.append(event_indices_ready, event_indices_after_minute)

            # Filter the original dataframe down to just this event, including the minute prior to the event starting
            # and the minute after the event ends (if the event is shorter than 11 minutes)
            event = df_1m.loc[event_indices_ready, :]
            
            # Reset the event indices according to:
            # The negative first minute starts at index -1.0
            # The event's first minute starts at index 0.0
            event.index = np.arange(-time_stamps_per_minute, event.shape[0] - time_stamps_per_minute, 1 / time_stamps_per_minute)

            # Call the perf_metrics() method to obtain key event metrics
            performance_results = self.perf_metrics(event, shorter_than_11_min)
            # Call the event_value() method to calculate the event's value
            value_result = self.event_value(performance_results['Time_Start'],performance_results['Time_End'],previous_event_end,performance_results['Duration_mins'],performance_results['Request_MW'],performance_results['Shortfall_MW'])

            # Create temporary dataframe to contain the results
            event_results_df = pd.DataFrame({
                'Time_Start': performance_results['Time_Start'],
                'Time_End': performance_results['Time_End'],
                'Duration_mins': performance_results['Duration_mins'],
                'Delta_Previous_Event_mins': (performance_results['Time_End'] - previous_event_end).seconds / 60.,
                'SRMCP_$/MW': value_result['Hourly_Price'],
                'Response_Max_MW': performance_results['Response_Max_MW'],
                'Response_Max_Time_mins': performance_results['Response_Max_Time_mins'],
                'Response_Committed_Time_mins': performance_results['Response_Committed_Time_mins'],
                'Response_Start_MW': performance_results['Response_Start_MW'],
                'Response_End_MW': performance_results['Response_End_MW'],
                'Response_First10Min_MW': performance_results['Response_First10Min_MW'],
                'Response_After11Min_MW': performance_results['Response_After11Min_MW'],
                'Response_After11Min_Ratio': performance_results['Response_After11Min_Ratio'],
                'Request_MW': performance_results['Request_MW'],
                'Shortfall_MW': performance_results['Shortfall_MW'],
                'Value_$': value_result['Value']},
                index=[performance_results['Time_Start']])
            # Append the temporary dataframe into the results_df
            results_df = pd.concat([results_df, event_results_df])
            # Plot event-specific results and save plot to file
            # We want the plot to start from the end of the previous event
            # and go until 10 minutes past the end of the current event
            plot_start = previous_event_end
            plot_end = performance_results['Time_End'] + timedelta(minutes=10)
            plot_df = df_1m.loc[(df_1m.Date_Time >= plot_start) & (df_1m.Date_Time <= plot_end), :]
            plot_dir = dirname(abspath(__file__)) + '\\plots\\'
            plot_filename = datetime.now().strftime('%Y%m%d') + '_event_starting_' + performance_results['Time_Start'].strftime('%Y%m%d-%H-%M-%S') + '.png'
            plt.figure(1)
            plt.subplot(211)
            plt.plot(plot_df.Date_Time, plot_df.Request, label='P Request')
            plt.plot(plot_df.Date_Time, plot_df.Response, label='P Response')
            plt.ylabel('Power (kW)')
            plt.legend(loc='best')
            plt.subplot(212)
            plt.plot(plot_df.Date_Time, plot_df.SoC, label='SoC')
            plt.ylabel('SoC (%)')
            plt.xlabel('Time')
            plt.savefig(plot_dir + plot_filename, bbox_inches='tight')
            plt.close()

            # Reset previous_end_end to be the end of this event before moving on to the next event
            previous_event_end = performance_results['Time_End'] 

        # For testing (with few events), showing the transposed dataframe is a bit easier to read   
        print(results_df.T)


        '''# Loop through each hour between "start_time" and "end_time".
                                while cur_time < end_time - timedelta(minutes=60):
                                    # Generate 1-hour worth of request and response arrays for calculating scores.
                                    cur_end_time = cur_time + timedelta(minutes=60)
                                    # Generate lists of synchronized reserve request and response class objects.
                                    request_list_1m_60min = [r for r in request_list_1m if cur_time <= r.ts_req <= cur_end_time]
                                    response_list_1m_60min = [r for r in response_list_1m if cur_time <= r.ts <= cur_end_time]
                                    # Convert lists into arrays.
                                    request_array_1m_60min = np.asarray(request_list_1m_60min)
                                    response_array_1m_60min = np.asarray(response_list_1m_60min)
                        
                                    list_event_ending_time = []
                                    t_end = None
                                    # Loop through request and response class objects to determine the "immediate past interval".
                                    for i in request_array_1m_60min:
                                        list_response_start_3min = []
                                        list_response_end_3min = []
                                        # How to link the request and response class objects with same timestamp?
                                        # How to get consective 3min values?
                                        P_responce = response_array_1m_60min
                                        if i.P_req > 0:
                                            t_end = i.ts_req
                                            # Record the "immediate past interval" btw the ending times of the last and current events.
                                            if len(request_array_1m_60min)>0:
                                                dt = t_end - request_array_1m_60min[-1]
                                            else:
                                                dt = t_end
                                        elif t_end is not None:
                                            list_event_ending_time.append(t_end)
                        
                        
                                    # Read and store hourly SRMCP price.
                                    hourly_SRMCP = self._clearing_price_helper.clearing_prices[cur_time]
                                    # TODO: (minor) consider a different time step for results - perhaps daily or monthly.
                                    # Calculate performance scores for current hour and store in a dictionary keyed by starting time.
                                    hourly_results[cur_time] = {}
                                    hourly_results[cur_time]['performance_score'] = self.perf_score(request_array_1m_60min, response_array_1m_60min)
                                    # TODO: (minor) remove line below if not needed.
                                    # hourly_results[cur_time]['hourly_integrated_MW'] = self.Hr_int_reg_MW(request_array_2s)
                                    hourly_results[cur_time]['Regulation_Market_Clearing_Price(RMCP)'] = hourly_SRMCP
                                    hourly_results[cur_time]['Reg_Clearing_Price_Credit'] = self.Reg_clr_pr_credit(hourly_results[cur_time]['Regulation_Market_Clearing_Price(RMCP)'],
                                                                                                                   hourly_results[cur_time]['performance_score'][0],
                                                                                                                   hourly_results[cur_time]['hourly_integrated_MW'])
                                    # Move to the next hour.
                                    cur_time += one_hour
                        
                                # Store request and response parameters in lists for plotting and printing to text files.
                                P_request = [r.P_req for r in request_list_1m_tot]
                                ts_request = [r.ts_req for r in request_list_1m_tot]
                                P_responce = [r.P_service for r in response_list_1m_tot]
                                SOC = [r.soc for r in response_list_1m_tot]
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


        return hourly_results'''

    # Returns lists of requests and responses at 1m intervals.
    def get_signal_lists(self, start_time, end_time):
        # TODO: (minor) replace the temporary test file name with final event signal file name.
        historial_signal_filename = "gmlc_events_2017_1min.xlsx"
        # Returns a DataFrame that contains historical signal data in the events data file.
        self._historial_signal_helper.read_and_store_historical_signals(historial_signal_filename)
        # Returns a Dictionary with datetime type keys.
        signals = self._historial_signal_helper.signals_in_range(start_time, end_time)

        sim_step = timedelta(minutes=1)
        requests = []
        responses = []

        # Call the "request" method to get 1-min responses in a list, requests are stored in a list as well.
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


    def perf_metrics (self, event, shorter_than_11_min):
        '''
        '''
        # Obtain the start and end time stamps of the event
        event_start = pd.Timestamp(event.Date_Time[0])
        event_end = pd.Timestamp(event.Date_Time.max())
        # Remove extra minute we added to the end if the original event was less than 11 minutes
        if shorter_than_11_min:
            event_end = event_end - timedelta(minutes = 1)
        # Calculate the event duration
        event_duration_mins = (event_end - event_start).seconds / 60.

        # Calculate time to max response
        event_response_max = event.loc[event.Date_Time >= event_start, 'Response'].max()
        event_response_max_index = event.loc[event.Response == event_response_max, :].index[0]
        event_response_max_time_mins = (pd.Timestamp(event.Date_Time[event_response_max_index]) - event_start).seconds / 60.

        # Calculate time to committed response
        try:
            # This will try to grab the event dataframe's index of the first time where the response matches (or exceeds) the request.
            # If no such index exists, skip down to the "except" call where np.inf will be returned (indicating that the response
            # never matched or exceeded the request during the event)
            event_response_committed_index = event.loc[(event.Date_Time >= event_start) & (event.Response >= event.Request), :].index[0]
            event_response_committed_time_mins = (pd.Timestamp(event.Date_Time[event_response_committed_index]) - event_start).seconds / 60.
        except: # If the response never matches the commitment, return infinity as an indicator
            event_response_committed_time_mins = np.inf

        # Calculate event response at the start, which is the minimum response value
        # at the start, +/- 1 minute.  We already added in an extra minute before the event
        # started, so now we just take the minimum response
        # of the first three minutes of our data frame (minutes -1, 0, and 1).
        event_start_df = event.loc[:1, :]
        event_response_start = event_start_df.Response.min()

        # Calculate the requested MW for the event, which will be used in shortfall calculations
        # The requested value should be constant over the whole event, so the mean() call here shouldn't really matter
        event_request_MW = event.loc[0:,:].Request.mean()

        # Now calculate other metrics
        if not(shorter_than_11_min):
            # Calculate event response at the 10-minute mark, which is the maximum
            # response value from minutes 9, 10, and 11.
            event_end_10min_df = event.loc[9:11, :]
            event_response_end = event_end_10min_df.Response.max()
            
            # Now calculate average reponse during first 10 minutes
            # This is the delta between the 10-minute mark and the start
            event_response_first10min = event_response_end - event_response_start

            # Now calculate the response for the after 11-minute mark
            # This is the average response from 11 minutes on
            event_response_after11min_df = event.loc[11:, :]
            event_response_after11min = event_response_after11min_df.Response.mean()
            # Calculate metric of response after 11 minutes
            event_response_after11min_ratio = (event_response_after11min - event_response_start) / (event_response_end - event_response_start)

            # Calculate shortfall
            '''If the ratio of response for first 11 minutes is >= 1 and if ratio of response for 11+ minutes is >= 0.95, then shortfall equals 0.
            If the ratio of responses for first 11 minutes is < 1, then shortfall = 
                (average request MW - average responded MW during 11+ minutes [** use max at end of event if short event **])'''

            # Calculate the response ratios for the first 10 minutes, and after 11 minutes
            event_ratio_first10min = event_response_first10min / event_request_MW
            event_ratio_after11min = event_response_after11min / event_request_MW

            # Use the logic from above comment 
            # Allow room for some numeric representation issues in the if statement
            if (event_ratio_first10min >= 0.99995) & (event_ratio_after11min >= 0.95):
                event_shortfall_MW = 0.
            else:
                event_shortfall_MW = event_request_MW - event_response_after11min
        else:
            # Calculate the event response over the last 3 minutes of the event (including the additional
            # minute we already added on)
            event_end_df = event.iloc[-3:, :]
            event_response_end = event_end_df.Response.max()

            # The event response for event shorter than 11 minutes is the delta between the event end
            # and the event start
            event_response = event_response_end - event_response_start
            
            # For ease of including in result dataframe, we'll still call this event_response_first10min
            event_response_first10min = event_response
            # The event is shorter than 11 minutes, so return NaN for these two metrics
            event_response_after11min = np.nan
            event_response_after11min_ratio = np.nan

            # Calculate the response ratio for the event
            event_ratio = event_response / event_request_MW
            
            # Calculate shortfall
            '''If the ratio of response for is >= 1 , then shortfall equals 0.
            If the ratio of response is < 1, then shortfall = 
                (average request MW - max response at end of event)'''

            # Allow room for some numeric representation issues
            if (event_ratio >= 0.99995):
                event_shortfall_MW = 0.
            else:
                event_shortfall_MW = event_request_MW - event_response_end
        
        return dict({
            'Time_Start':event_start,
            'Time_End':event_end,
            'Duration_mins':event_duration_mins,
            'Response_Max_MW':event_response_max,
            'Response_Max_Time_mins':event_response_max_time_mins,
            'Response_Committed_Time_mins':event_response_committed_time_mins,
            'Response_Start_MW':event_response_start,
            'Response_End_MW':event_response_end,
            'Response_First10Min_MW':event_response_first10min,
            'Response_After11Min_MW':event_response_after11min,
            'Response_After11Min_Ratio':event_response_after11min_ratio,
            'Request_MW':event_request_MW,
            'Shortfall_MW':event_shortfall_MW})

    def event_value(self, time_start, time_end, previous_event_end, event_duration_mins, event_request_MW, event_shortfall_MW):
        ''' Method to calculate an event's value, whic his based on the requested MW for the event, the event duration,
        the event's shortfall (in MW), the time between the current event's end and the previous event's end, and
        the hourly price.
        '''
        # Ensure the event happens within a given hour, otherwise further consideration will need to happen
        # to account for pricing
        if (time_start.day == time_end.day) & (time_start.month == time_end.month) & (time_start.hour == time_end.hour):
            hourly_SRMCP = self._clearing_price_helper.clearing_prices[time_start.replace(minute=0)][0]
        else:
            print('WARNING: Event spans multiple hours (or possibly days)...Need to do something here')

        # Calculate the time between this event's end and the previous event's end (in hours)
        # This will be used to calculate the shortfall, if necessary
        time_bw_event_ends_hr = (time_end - previous_event_end).seconds / 3600.

        # Calculate value of event
        event_value = ((event_request_MW * event_duration_mins / 60.) - (event_shortfall_MW * time_bw_event_ends_hr)) * hourly_SRMCP
        return dict({
            'Value': event_value,
            'Hourly_Price': hourly_SRMCP})


    # Based on PJM Manual 28 (need to verify definition, not found in manual).
    def Hr_int_reg_MW (self, input_sig):
        # Take one hour of 2s RegA data
        Hourly_Int_Reg_MW = np.absolute(input_sig).sum() * 2 / 3600
        # print(Hourly_Int_Reg_MW)
        return Hourly_Int_Reg_MW



    # Calculate an hourly value of "Synchronized Reserve Market Clearing Price (SRMCP) Credit" for the service provided.
    # Based on PJM Manual 28.
    def Reg_clr_pr_credit(self, RM_pr, pf_score, reg_MW):
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
        # if pf_score < 0.25:
        #     Reg_RMCCP_Credit = 0
        #     Reg_RMPCP_Credit = 0
        # else:
        #     Reg_RMCCP_Credit = reg_MW * pf_score * RMCCP
        #     Reg_RMPCP_Credit = reg_MW * pf_score * mi_ratio * RMPCP
        # Reg_Clr_Pr_Credit = Reg_RMCCP_Credit + Reg_RMPCP_Credit

        # # for debug use
        # print("Reg_Clr_Pr_Credit:", Reg_Clr_Pr_Credit)
        # print("Reg_RMCCP_Credit:", Reg_RMCCP_Credit)
        # print("Reg_RMPCP_Credit:", Reg_RMPCP_Credit)

        # "Lost opportunity cost credit" (for energy sources providing regulation) is not considered,
        # because it does not represent economic value of the provided service.

        return (Reg_Clr_Pr_Credit, Reg_RMCCP_Credit, Reg_RMPCP_Credit)



    # Use "dependency injection" to allow method "fleet" be used as an attribute.
    @property
    def fleet(self):
        return self._fleet

    @fleet.setter
    def fleet(self, value):
        self._fleet = value


# Run from this file.
if __name__ == '__main__':
    from fleets.battery_inverter_fleet.battery_inverter_fleet import BatteryInverterFleet
    from grid_info import GridInfo
    service = ReserveService()

    # fleet = BatteryInverterFleet('C:\\Users\\jingjingliu\\gmlc-1-4-2\\battery_interface\\src\\fleets\\battery_inverter_fleet\\config_CRM.ini')
    grid = GridInfo('Grid_Info_DATA_2.csv')
    battery_inverter_fleet = BatteryInverterFleet(
        GridInfo=grid)  # establish the battery inverter fleet with a grid.
    service.fleet = battery_inverter_fleet

    # Use line below for testing DYNAMIC regulation service.
    fleet_response = service.request_loop(start_time=parser.parse("2017-08-01 16:00:00"),
                                          end_time=parser.parse("2017-08-02 15:00:00"))

    # Print results in the 2-level dictionary.
    for key_1, value_1 in fleet_response.items():
        print(key_1)
        for key_2, value_2 in value_1.items():
            print('\t\t\t\t\t\t', key_2, value_2)

# cd C:\Users\jingjingliu\gmlc-1-4-2\battery_interface\src\services\reserve_service\
# python reserve_service.py

