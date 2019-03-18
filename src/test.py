# -*- coding: utf-8 -*- {{{
#
# Your license here
# }}}

import sys
from datetime import datetime
from dateutil import parser
import pandas as pd
import matplotlib.pyplot as plt
from os.path import dirname, abspath, join

sys.path.insert(0, dirname(dirname(dirname(abspath(__file__)))))

from fleet_factory import create_fleet
from service_factory import create_service


def integration_test(service_name, fleet_name, service_type='Traditional', **kwargs):
    # Create test service
    service = create_service(service_name)
    if service is None:
        raise 'Could not create service with name ' + service_name

    grid_type = 1
    if service_name == 'ArtificialInertia':
        grid_type = 2

    # Create test fleet
    fleet = create_fleet(fleet_name, grid_type, **kwargs)
    if fleet is None:
        raise 'Could not create fleet with name ' + fleet_name

    # Assign test fleet to test service to use
    service.fleet = fleet
    assigned_fleet_name = service.fleet.__class__.__name__

    # Run test
    if service_name == 'Regulation':
        monthtimes = dict({
            # 'January': ["2017-01-01 00:00:00", "2017-01-31 23:59:59"],
            # 'February': ["2017-02-01 00:00:00", "2017-02-28 23:59:59"],
            # 'March': ["2017-03-01 00:00:00", "2017-03-31 23:59:59"],
            # 'April': ["2017-04-01 00:00:00", "2017-04-30 23:59:59"],
            # 'May': ["2017-05-01 00:00:00", "2017-05-31 23:59:59"],
            # 'June': ["2017-06-01 00:00:00", "2017-06-30 23:59:59"],
            # 'July': ["2017-07-01 00:00:00", "2017-07-31 23:59:59"],
            'August': ["2017-08-01 16:00:00", "2017-08-01 18:59:59"],
            # 'September': ["2017-09-01 00:00:00", "2017-09-30 23:59:59"],
            # 'October': ["2017-10-01 00:00:00", "2017-10-31 23:59:59"],
            # 'November': ["2017-11-01 00:00:00", "2017-11-30 23:59:59"],
            # 'December': ["2017-12-01 00:00:00", "2017-12-31 23:59:00"]
        })

        all_results = pd.DataFrame(columns=['performance_score', 'hourly_integrated_MW',
                                        'mileage_ratio', 'Regulation_Market_Clearing_Price(RMCP)',
                                        'Reg_Clearing_Price_Credit'])
        for month in monthtimes.keys():
            print('Starting ' + str(month) + ' ' + service_type + ' at ' + datetime.now().strftime('%H:%M:%S'))
            fleet_response = service.request_loop(service_type=service_type,
                                                    start_time=parser.parse(monthtimes[month][0]),
                                                    end_time=parser.parse(monthtimes[month][1]),
                                                    clearing_price_filename='historical-ancillary-service-data-2017.xls',
                                                    fleet_name=fleet_name)
            month_results = pd.DataFrame.from_dict(fleet_response, orient='index')
            all_results = pd.concat([all_results, month_results])
            print('     Finished ' + str(month) + ' ' + service_type)
        # Fix formatting of all_results dataframe to remove tuples
        all_results[['Perf_score', 'Delay_score', 'Corr_score', 'Prec_score']] = all_results['performance_score'].apply(
            pd.Series)
        all_results[['MCP', 'REG_CCP', 'REG_PCP']] = all_results['Regulation_Market_Clearing_Price(RMCP)'].apply(
            pd.Series)
        all_results[['Reg_Clr_Pr_Credit', 'Reg_RMCCP_Credit', 'Reg_RMPCP_Credit']] = all_results[
            'Reg_Clearing_Price_Credit'].apply(pd.Series)
        all_results.drop(
            columns=['performance_score', 'Regulation_Market_Clearing_Price(RMCP)', 'Reg_Clearing_Price_Credit'],
            inplace=True)
        print('Writing result .csv')
        file_dir = join(dirname(abspath(__file__)), 'services', 'reg_service', 'results', '')
        all_results.to_csv(file_dir + datetime.now().strftime(
            '%Y%m%d') + '_annual_hourlyresults_' + service_type + '_' + fleet_name + '.csv')

    elif service_name == 'Reserve':
        monthtimes = dict({
            'January': ["2017-01-08 00:00:00", "2017-01-08 23:59:59"],
            # 'February': ["2017-02-01 00:00:00", "2017-02-28 23:59:59"],
            # 'March': ["2017-03-01 00:00:00", "2017-03-31 23:59:59"],
            # 'April': ["2017-04-01 00:00:00", "2017-04-30 23:59:59"],
            # 'May': ["2017-05-01 00:00:00", "2017-05-31 23:59:59"],
            # 'June': ["2017-06-01 00:00:00", "2017-06-30 23:59:59"],
            # 'July': ["2017-07-01 00:00:00", "2017-07-31 23:59:59"],
            # 'August': ["2017-08-01 00:00:00", "2017-08-31 23:59:59"],
            # 'September': ["2017-09-01 00:00:00", "2017-09-30 23:59:59"],
            # 'October': ["2017-10-01 00:00:00", "2017-10-31 23:59:59"],
            # 'November': ["2017-11-01 00:00:00", "2017-11-30 23:59:59"],
            # 'December': ["2017-12-01 00:00:00", "2017-12-31 23:59:00"]
        })

        all_results = pd.DataFrame(columns=['Event_Start_Time', 'Event_End_Time',
                                            'Response_to_Request_Ratio', 'Response_MeetReqOrMax_Index_number',
                                            'Event_Duration_mins', 'Response_After10minToEndOr30min_To_First10min_Ratio',
                                            'Requested_MW', 'Responded_MW_at_10minOrEnd', 
                                            'Responded_MW_After10minToEndOr30min', 'Shortfall_Ratio',
                                            'Response_0min_Min_MW', 'Response_10minOrEnd_Max_MW',
                                            'Response_After10minToEnd_MW', 'Avg_Ramp_Rate', 'Best_Ramp_Rate',
                                            'SRMCP_DollarsperMWh_DuringEvent',
                                            'SRMCP_DollarsperMWh_SinceLastEvent',
                                            'Service_Value_NotInclShortfall_dollars',
                                            'Service_Value_InclShortfall_dollars',
                                            'Period_from_Last_Event_Hours',
                                            'Period_from_Last_Event_Days'])
        if 'battery' in fleet_name.lower():
            annual_signals = pd.DataFrame(columns=['Date_Time', 'Request', 'Response', 'SoC'])
        else:
            annual_signals = pd.DataFrame(columns=['Date_Time', 'Request', 'Response'])

        previous_event_end = pd.Timestamp('01/01/2017 00:00:00')
        for month in monthtimes.keys():
            print('Starting ' + str(month) + ' at ' + datetime.now().strftime('%H:%M:%S'))
            start_time = parser.parse(monthtimes[month][0])
            fleet_response = service.request_loop(start_time=start_time,
                                                  end_time=parser.parse(monthtimes[month][1]),
                                                  clearing_price_filename=start_time.strftime('%Y%m') + '.csv',
                                                  previous_event_end=previous_event_end,
                                                  four_scenario_testing=False,
                                                  fleet_name=assigned_fleet_name)
            try:
                previous_event_end = fleet_response[0].Event_End_Time[-1]
            except:
                # If the dataframe in fleet_response[0] has no entries, then attempting
                # to index the Event_End_Time column will throw an error.  This allows
                # for skipping past that error.
                pass

            all_results = pd.concat([all_results, fleet_response[0]], sort=True)
            annual_signals = pd.concat([annual_signals, fleet_response[1]], sort=True)
        print('Writing event results .csv')
        file_dir = join(dirname(abspath(__file__)), 'integration_test', 'reserve_service')
        all_results.to_csv(join(file_dir,
                                datetime.now().strftime('%Y%m%d') + '_event_results_reserve_' + fleet_name + '.csv'))
        print('Plotting annual signals and SOC (if necessary)')
        plot_dir = file_dir
        plot_filename = datetime.now().strftime('%Y%m%d') + '_annual_signals_' + fleet_name + '.png'
        plt.figure(1)
        plt.figure(figsize=(15, 8))
        plt.subplot(211)
        if not(all(pd.isnull(annual_signals['Request']))):
            plt.plot(annual_signals.Date_Time, annual_signals.Request, label='P_Request')
        if not(all(pd.isnull(annual_signals['Response']))):
            plt.plot(annual_signals.Date_Time, annual_signals.Response, label='P_Response')
        if not(all(pd.isnull(annual_signals['P_togrid']))):
            plt.plot(annual_signals.Date_Time, annual_signals.P_togrid, label='P_togrid')
        if not(all(pd.isnull(annual_signals['P_base']))):
            plt.plot(annual_signals.Date_Time, annual_signals.P_base, label='P_base')
        plt.ylabel('Power (MW)')
        plt.legend(loc='best')
        if 'battery' in fleet_name.lower():
            if not(all(pd.isnull(annual_signals['SoC']))):
                plt.subplot(212)
                plt.plot(annual_signals.Date_Time, annual_signals.SoC, label='SoC')
                plt.ylabel('SoC (%)')
                plt.xlabel('Time')
        plt.savefig(join(plot_dir, plot_filename), bbox_inches='tight')
        plt.close()
        print('Saving .csv of annual signals and SOC (if necessary)')
        annual_signals.to_csv(
            join(file_dir,
                 datetime.now().strftime('%Y%m%d') + '_annual_signals_reserve_' + fleet_name + '.csv'))

    elif service_name == 'ArtificialInertia':
        fleet_responses = service.request_loop()
        avg = service.calculation(fleet_responses)
        print(avg)

    else:
        pass


if __name__ == '__main__':
    # Full test
    # services = ['Regulation', 'Reserve', 'ArtificialInertia']
    # fleets = ['BatteryInverter', 'ElectricVehicle', 'PV', 'WaterHeater', 'HVAC', 'Refridge' ]
    # service_types = ['Traditional', Dynamic'] # This is only useful for regulation service
    # kwargs = {'autonomous': True}  # This is for later use

    # Dev test
    services = ['Regulation']
    fleets = ['BatteryInverter']
    service_types = ['Traditional']
    kwargs = {}

    for service in services:
        for fleet in fleets:
            for service_type in service_types:
                integration_test(service, fleet, service_type, **kwargs)
