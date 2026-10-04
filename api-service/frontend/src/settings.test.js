import {describe,it,expect} from 'vitest';
import {settingChangeText} from './settings';
describe('setting change units',()=>{
 it('uses positive drop magnitudes and explicit units',()=>{
  expect(settingChangeText('expected_high_percentage',20)).toBe('20%');
  expect(settingChangeText('expected_low_percentage',-12)).toBe('12%');
  expect(settingChangeText('highest_price_reference_days',60)).toBe('60일');
  expect(settingChangeText('volume_check',false)).toBe('미사용');
 });
});
