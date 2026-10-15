import { patch } from "@web/core/utils/patch";
import { PartnerAutoCompleteCharField } from "@partner_autocomplete/js/partner_autocomplete_fieldchar";

patch(PartnerAutoCompleteCharField.prototype, {
    async onSelectPartnerAutocompleteOption(option) {
        let data = await this.partnerAutocomplete.getCreateData(option);
        if (!data?.company) {
            return;
        }

        if (data.logo) {
            const logoField = this.props.record.resModel === 'res.partner' ? 'image_1920' : 'logo';
            data.company[logoField] = data.logo;
        }

        // Save UNSPSC codes (tags)
        const unspsc_codes = data.company.unspsc_codes;

        // Delete useless fields before updating record
        data.company = this.partnerAutocomplete.removeUselessFields(data.company, Object.keys(this.props.record.fields));

        // Add UNSPSC codes (tags)
        if (this.props.record.resModel === 'res.partner' && unspsc_codes && unspsc_codes.length !== 0) {
            // category id is fetched and then tags are created (many2many)
            const category_id = await this.orm.call("res.partner", "iap_partner_autocomplete_get_tag_ids", [this.props.record.resId, unspsc_codes]);
            data.company['category_id'] = [[6, 0, category_id]];
        }

        // Update record with retrieved values
        if (data.company.name) {
            await this.props.record.update({ name: data.company.name });  // Needed otherwise name is not saved
        }
        await this.props.record.update(data.company);

        if (this.props.setDirty) {
            this.props.setDirty(false);
        }
    }
});
